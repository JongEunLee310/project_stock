# Codex Handoff Task

## Source Issue

BE #187 (Epic BE #174 6단계). 설계 `docs/designs/072-context-builder.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md` §6.7·§7·§11(6단계)·§13.

## Task Summary

LLM 데이터 파이프라인 6단계. 여러 도메인에 흩어진 데이터를 모아 LLM 직전 입력인 `LLMContextBundle`을
조립하는 `ContextBuilder`를 기존 도메인 `app/domains/llm_context/`에 도메인 서비스로 신설한다.
계약(`app/domains/llm_context/schema.py`)과 5단계 `PriceFeatureBuilder`를 소비하고, 소스가 부족하면
예외 없이 `None`·빈 값·data_quality 경고로 degrade한다. 뉴스·시그널은 이번 단계에서 배선하지 않고
빈 리스트로 둔다(Core slice).

## Goal

- `app/domains/llm_context/context_builder.py`에 `ContextBuilder`와 §11(6단계) 4개 메서드가 존재한다.
- `build_context_bundle(...)`가 Pydantic 검증을 통과하는 `LLMContextBundle`을 생성하고 필수 필드를
  빠뜨리지 않는다.
- 자산·bar·포트폴리오·decision-log 결손 시 예외 없이 degrade하고 data_quality에 상태·warning을 남긴다.
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head `c3d4e5f60058` 유지(마이그레이션 없음).

## Background

계약은 이미 존재한다(`app/domains/llm_context/schema.py`): `LLMContextBundle`, `SymbolCard`,
`PriceSnapshot`, `PortfolioContext`, `PortfolioSummary`, `RecentNewsItem`, `SignalItem`,
`RecentDecision`, `DataQualitySection`, `DataQualityStatus`, `OutputContract`. 스냅샷·비중 필드는
`float | None`이므로 내부 `Decimal` 값은 `float()`로 변환해 담는다.

재사용할 기존 소스(모두 읽기 전용):

- 자산: `app/domains/assets/repository.py` `AssetRepository.get_by_symbol_market(symbol, market)
  -> Asset | None`. `Asset.name`이 display_name, `Asset.market`이 market.
- 가격: `app/domains/prices/repository.py` `PriceBarRepository.list_recent(symbol, market,
  interval, limit) -> list[StockPriceBar]`(timestamp 오름차순). 5단계 빌더
  `app/domains/features/price_builder.py` `PriceFeatureBuilder.build(bars) -> PriceFeatureSet`.
- 포트폴리오: `app/domains/portfolios/repository.py` `PortfolioRepository.list_by_user(user_id)`,
  `app/domains/portfolios/service.py` `PortfolioService.get_summary(portfolio_id, user_id)
  -> PortfolioSummaryResponse`(내부에서 시세를 반영해 `positions[].weight`·`market_value`·
  `cost_value`·`cash_weight`·`has_sector_concentration`·`concentration_threshold`·
  `positions[].exceeds_threshold`를 이미 계산). 재계산하지 말고 이 요약을 매핑만 한다.
- decision-log: `app/domains/decision_logs/repository.py` `DecisionLogRepository.list_by_user(
  user_id, limit=..., sort="-decided_at")`. 심볼 필드는 `ticker`(주의: `symbol` 아님), 시각은
  `decided_at`.

## Implementation Scope

신규:

- `app/domains/llm_context/user_rules.py`: `DEFAULT_USER_RULES: list[str]` — 기준 문서 §14 기본
  규칙 목록 상수.
- `app/domains/llm_context/context_builder.py`: `ContextBuilder`. 생성자에 `Session`을 주입받아
  필요한 리포지토리/서비스를 구성한다. 메서드:
  - `build_symbol_context(user_id: int, symbol: str, market: str) -> SymbolCard`
  - `build_portfolio_context(user_id: int) -> PortfolioSummary | None`
  - `build_recent_decision_context(user_id: int, symbol: str) -> list[RecentDecision]`
  - `build_context_bundle(task_type: LLMTaskType, user_id: int, symbols: list[tuple[str, str]])
    -> LLMContextBundle` — `symbols`는 `(symbol, market)` 쌍 목록(Decision EE).

메서드별 매핑:

- `build_symbol_context`:
  - 자산 조회로 `display_name`(=`Asset.name`) 확보. 자산 미존재여도 예외 금지(빈 display_name 등
    안전 기본값 + data_quality 반영은 상위에서).
  - `list_recent(symbol, market, interval="1d", limit=_PRICE_BAR_LIMIT)`로 bar 조회 →
    `PriceFeatureBuilder().build(bars)`로 피처 산출. `PriceSnapshot.close`는 최신 bar
    `close_price`, 나머지는 피처값. bar가 없으면 모든 스냅샷 필드 `None`.
  - `portfolio_context`: 해당 자산의 보유 포지션이 있으면 `holding=True`, `weight`←position weight,
    `avg_buy_price`←position avg_buy_price, `unrealized_return`←`(market_value - cost_value) /
    cost_value`(cost_value 0이면 `None`). 미보유면 `None`.
  - `recent_news=[]`, `signals=[]`(Decision AA).
- `build_portfolio_context`: `list_by_user(user_id)`의 첫 포트폴리오로 `get_summary` 호출 →
  `cash_ratio`←`cash_weight`, `top_holding_weight`←`positions[].weight` 최댓값(포지션 없으면
  `None`), `concentration_risk`←파생 문자열(임의 position `exceeds_threshold` → `"high"`, 아니면
  `has_sector_concentration` → `"medium"`, 그 외 `"low"`). 내부 요약과 동일 척도를 유지하고 스케일
  변환은 하지 않는다. 포트폴리오 부재면 `None`.
- `build_recent_decision_context`: `list_by_user(user_id, limit=_RECENT_DECISION_LIMIT,
  sort="-decided_at")` 결과에서 `ticker == symbol`인 것만 골라 `RecentDecision`(`symbol`←`ticker`,
  `decision_type`←`decision_type`, `reason`←`reason or ""`, `created_at`←`decided_at`)로 매핑.
- `build_context_bundle`: 각 `(symbol, market)`마다 `build_symbol_context`로 `symbol_cards` 구성 +
  `build_portfolio_context` + symbol별 `build_recent_decision_context` 합류 + `user_rules`←
  `DEFAULT_USER_RULES` + `data_quality` 산출 + `output_contract`(§7 required_fields) +
  `as_of`=현재 시각 + `user_intent`=task_type 기본 문구 + `symbols`=요청 심볼 목록.

data_quality 산출(§13):

- `price_data_status`: 어느 symbol이든 bar가 충분하면 `valid`, 일부만 있으면 `partial`, 전무하면
  `missing`.
- `news_data_status`: 항상 `missing`, `warnings`에 "뉴스 데이터는 아직 포함되지 않았습니다." 추가
  (Decision AA).
- `portfolio_data_status`: 포트폴리오·포지션 존재 시 `valid`, 부재 시 `missing`.

상수: `_PRICE_BAR_LIMIT = 252`, `_RECENT_DECISION_LIMIT`(예: 5) 등 모듈 상수로 둔다.

수정: 없음(기존 파일 변경 없음).

## Out of Scope

- 뉴스·시그널 배선(`recent_news`·`signals` 채우기) — 6.5 후속(Decision AA).
- `LLMContextBundle` 영속·`input_context_json` 저장 — 7단계 `llm_analysis`.
- route/endpoint 노출 — 지침 §19 "route는 마지막".
- `UserRule` 모델·마이그레이션(Decision BB), 신규 alembic revision.
- `PortfolioFeatureBuilder`·`NewsFeatureBuilder` 신설.
- 포트폴리오 비중·시세 재계산(기존 `get_summary` 재사용).

## Protected Files

- 기존 소스 도메인 `app/domains/assets/*`·`app/domains/prices/*`·`app/domains/portfolios/*`·
  `app/domains/decision_logs/*`·`app/domains/features/*`·`app/domains/news/*`·
  `app/domains/signals/*` — 참조만, 수정 금지.
- `app/domains/llm_context/schema.py`·`app/domains/llm_analysis/*`·`app/adapters/llm/*` — 변경 금지
  (계약 소비만).
- `alembic/versions/*` — 신규 revision 금지.
- route/`app/api/*` — 이번 단계에서 건드리지 않는다.

## Requirements

- `ContextBuilder`는 읽기 전용. 어떤 쓰기·커밋도 하지 않는다.
- 반환·중간 타입 이름에 `Dto`를 쓰지 않는다(projection 네이밍).
- 모든 소스 결손(자산·bar·포트폴리오·decision 부재, 분모 0)에서 예외를 던지지 않고 `None`·빈 값·
  data_quality 경고로 degrade한다.
- 스냅샷·비중의 `Decimal` 값은 `float()`로 변환해 스키마(`float | None`)에 담는다.
- 타입 주석 완전화(mypy `no-untyped-def` 회피). `Decimal`/`float` 나눗셈 0 분모 가드.

## Test Requirements

- `tests/test_context_builder.py`(신규), `db` 세션 fixture 사용:
  - `build_context_bundle`가 가격·포트폴리오·decision-log가 준비된 상태에서 Pydantic 검증을
    통과하는 `LLMContextBundle`을 만들고 필수 필드를 빠뜨리지 않는다.
  - bar 충분 시 `price_snapshot.close`·피처가 채워지고, bar 없으면 스냅샷 `None` +
    `price_data_status=missing`.
  - 보유 종목이면 `portfolio_context`(holding·weight·avg_buy_price·unrealized_return)가 채워지고,
    미보유면 `None`.
  - 해당 symbol의 최근 decision-log가 `recent_decisions`로 매핑되고, 없으면 빈 리스트.
  - `news_data_status=missing` + 뉴스 부재 warning이 표기된다.
  - 자산·포트폴리오 부재 등 결손 입력에서 예외 없이 degrade한다.
- 필요한 엔티티(User·Asset·StockPriceBar·Portfolio·Position·DecisionLog)는 fixture/직접 생성으로
  준비한다. 외부 API 호출 없이 통과해야 한다.

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head c3d4e5f60058 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/072-context-builder.md`·본 핸드오프가 같은 PR에 포함된다. 지침서 §11 6단계 서술의
완료 갱신은 Epic 마무리 시점에 함께 한다(지금 별도 갱신 불필요).

## ADR Need

불필요. 1단계 계약을 채우는 통상 조립 작업으로, 미영속·projection 네이밍·순수/부수효과 분리 등 기존
결정의 연장선이다.

## Failure Record Need

불필요. 신규 기능 구현이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Low-Medium. 기존 파일 수정·마이그레이션·쓰기가 없는 신규 읽기 전용 서비스라 회귀 위험은 낮다. 관건은
여러 소스의 계약 매핑 정확성(특히 decision-log `ticker`, `Decimal→float` 변환)과 결손 시 graceful
degradation, data_quality 산출의 정확성이다.

## Decisions 요약 (설계 072 참조)

- **EE. symbols는 (symbol, market) 쌍 목록**: `build_context_bundle`의 `symbols`는 `list[tuple[str,
  str]]`로 받아 심볼별 market을 확보한다(자산·가격 조회에 market이 필요).
- **AA. 뉴스·시그널 후속**: `recent_news`·`signals`는 빈 리스트, data_quality로 부재 표기.
- **Z. 미영속·route 미노출**: 저장·엔드포인트 없음, 단일 head 유지.
- **BB. user_rules 상수**: `DEFAULT_USER_RULES` 상수, UserRule 모델 미도입.

## Expected Output

신규 2개 파일(`user_rules.py`·`context_builder.py`) + 신규 테스트 1개. 검증 명령 4종 결과와 함께
요약.
