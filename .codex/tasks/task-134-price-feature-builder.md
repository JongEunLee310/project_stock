# Codex Handoff Task

## Source Issue

BE #185 (Epic BE #174 5단계). 설계 `docs/designs/071-price-feature-builder.md`. 기준 문서
`docs/knowledge/llm-data-pipeline.md` §5단계·§6.5.

## Task Summary

LLM 데이터 파이프라인 5단계. LLM에 넣기 전에 계산 가능한 가격 지표를 만드는 `PriceFeatureBuilder`를
신규 도메인 `app/domains/features/`에 순수·무상태 컴포넌트로 신설한다. 초기 가격 피처 5종을
계산하고, 이력이 부족하면 안전하게 `None`을 반환한다.

## Goal

- 신규 도메인 `app/domains/features/`에 `PriceFeatureSet` projection과 `PriceFeatureBuilder`가
  존재한다.
- `PriceFeatureBuilder.build(bars)`가 초기 가격 피처 5종(`return_1d`/`return_5d`/`return_20d`/
  `volume_vs_20d_avg`/`drawdown_from_52w_high`)을 계산한다.
- 이력 부족·분모 0이면 해당 피처만 `None`이고 예외를 던지지 않는다.
- CI 3종(ruff + mypy + pytest) 통과, alembic 단일 head `c3d4e5f60058` 유지(마이그레이션 없음).

## Background

- 가격 bar는 `app/domains/prices/model.py`의 `StockPriceBar`(`stock_price_bars`)에 정규화·검증되어
  저장된다. 필드: `symbol`/`market`/`interval`/`timestamp`/`open_price`/`high_price`/`low_price`/
  `close_price`/`adjusted_close_price`/`volume`/`currency`/`source`.
- `PriceBarRepository.list_recent(symbol, market, interval, limit)`이 timestamp 오름차순으로
  반환한다(참조용, 이번 단계에서 배선하지는 않는다).
- 이번 단계는 순수 빌더 + projection + 단위 테스트만. 소비 배선(어느 service/job이 조회해 피처를
  쓰는지)은 6단계 ContextBuilder의 몫이라 포함하지 않는다(설계 Decision R).
- 피처는 영속하지 않는다(설계 Decision V, 4단계 Decision Q 계승). 마이그레이션 없음.

## Implementation Scope

신규:

- `app/domains/features/__init__.py`.
- `app/domains/features/schema.py`: `PriceFeatureSet` projection(Pydantic `BaseModel` 또는 frozen
  dataclass). 필드 5종 모두 `Decimal | None`:
  `return_1d`, `return_5d`, `return_20d`, `volume_vs_20d_avg`, `drawdown_from_52w_high`.
- `app/domains/features/price_builder.py`: `PriceFeatureBuilder`(순수·무상태).
  - `build(bars: list[StockPriceBar]) -> PriceFeatureSet`.
  - 입력을 `timestamp` 기준 오름차순으로 방어적 재정렬.
  - 피처 정의(기준가는 `close_price`, 52주 최고가는 `high_price` — Decision W):
    - `return_1d = (close[-1] - close[-2]) / close[-2]`, 필요 bar ≥ 2.
    - `return_5d = (close[-1] - close[-6]) / close[-6]`, 필요 bar ≥ 6.
    - `return_20d = (close[-1] - close[-21]) / close[-21]`, 필요 bar ≥ 21.
    - `volume_vs_20d_avg = volume[-1] / mean(volume of last 20 bars)`, 필요 bar ≥ 20.
    - `drawdown_from_52w_high = (close[-1] - max(high of last 252 bars)) / max(high of last 252 bars)`,
      필요 bar ≥ 1(가용한 최근 최대 252 bar에서 최고가 계산).
  - 필요 bar 수 미달·분모(기준 종가·평균 거래량·최고가) 0이면 해당 피처 `None`. 예외 금지.
  - 윈도우 상수는 모듈 상수로 둔다(`_VOLUME_AVG_WINDOW = 20`, `_HIGH_WINDOW_52W = 252` 등).
  - 계산은 `Decimal`로 수행(가격 필드가 `Numeric`/`Decimal`, 정밀도 유지).

수정: 없음(기존 파일 변경 없음).

## Out of Scope

- `PortfolioFeatureBuilder`·`NewsFeatureBuilder` 및 스텁(Decision S).
- 피처 조회·소비 배선(service/repository/job/ContextBuilder) — 6단계.
- 피처 영속 테이블, 신규 alembic revision(Decision V).
- adjusted_close 기반 정교화, moving_average·volatility 등 §6.5 확장 피처.
- Signal Detection Layer(§6.6).
- 기존 도메인(`prices`/`news`/`ingestion` 등) 파일 수정.

## Protected Files

- `app/domains/prices/*`·`app/domains/news/*`·`app/domains/ingestion/*` — 참조만, 수정 금지.
- `app/domains/analysis/*`·`app/domains/llm_context/*`·`app/domains/llm_analysis/*`·
  `app/domains/decision_logs/*`·`app/adapters/llm/*`·`app/domains/raw_prices/*`·
  `app/domains/raw_news/*` — 변경 금지.
- `alembic/versions/*` — 신규 revision 금지.

## Requirements

- `PriceFeatureBuilder`는 DB·세션 비의존 순수 컴포넌트. `StockPriceBar` 인스턴스를 읽기만 한다.
- 반환 타입 이름에 `Dto`를 쓰지 않는다(projection 네이밍).
- 모든 피처는 이력 부족·분모 0에서 `None`으로 graceful degrade. 빌더는 예외를 던지지 않는다.
- 타입 주석 완전화(mypy `no-untyped-def` 회피). `Decimal` 나눗셈 시 0 분모 가드.

## Test Requirements

- `tests/test_price_feature_builder.py`(신규):
  - 충분한 이력(≥252 bar 합성)에서 5종 피처가 기대 계산과 일치.
  - 이력 부족(예: 1 bar)에서 수익률·평균 피처가 `None`, 경계(정확히 필요 최소 bar)에서 값 산출.
  - 분모 0(기준 종가 0 또는 평균 거래량 0)에서 해당 피처 `None`.
  - 역순 입력이 재정렬 후 오름차순과 동일 결과.
- 테스트는 DB 없이 `StockPriceBar` 인스턴스를 직접 구성해 돌린다(세션 불필요).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`
- `uv run alembic heads`  # 단일 head c3d4e5f60058 확인(마이그레이션 없음)

## Documentation Impact

설계 `docs/designs/071-price-feature-builder.md`·본 핸드오프가 같은 PR에 포함된다. 지침서 §11
5단계 서술의 완료 갱신은 Epic 마무리 시점에 함께 한다(지금 별도 갱신 불필요).

## ADR Need

불필요. 신규 도메인에 순수 계산 컴포넌트를 추가하는 통상 작업으로, 1~4단계 합의(순수/부수효과
분리·미영속·projection 네이밍)의 연장선이다.

## Failure Record Need

불필요. 신규 기능 구현이며 알려진 실패 패턴 대응이 아니다.

## Risk Level

Low. 기존 파일 수정·마이그레이션·배선이 없는 순수 신규 컴포넌트라 회귀 위험이 낮다. 관건은 피처
정의(윈도우·분모 가드)와 graceful degradation 경계의 정확성이다.

## Expected Output

신규 3개 파일(`__init__.py`·`schema.py`·`price_builder.py`) + 신규 테스트 1개. 검증 명령 4종
결과와 함께 요약.
