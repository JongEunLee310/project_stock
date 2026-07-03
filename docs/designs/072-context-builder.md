# 072 · LLM 데이터 파이프라인 6단계 — ContextBuilder (LLMContextBundle 조립)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), 구현 이슈 BE #187,
Milestone 데이터 수집 파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`
(§6.7·§7·§11(6단계)·§13). 선행 설계 `docs/designs/071-price-feature-builder.md`(5단계 Decision
R·V — 소비 배선은 6단계 몫).

## 1. 배경

1단계에서 `LLMContextBundle` 계약(`app/domains/llm_context/schema.py`)을, 5단계에서
`PriceFeatureBuilder`(#185)를 각각 완성했다. 이제 여러 도메인에 흩어진 데이터를 모아 LLM 직전
입력인 `LLMContextBundle`을 조립하는 ContextBuilder가 필요하다. 지침 §6.7은 이 계층을 "LLM 직전의
가장 중요한 계층"으로, 가격 피처·뉴스 요약·포트폴리오 상태·사용자 규칙·과거 decision-log·데이터
신뢰도 상태를 모아 task_type에 맞는 번들을 만드는 책임으로 정의한다.

계약(`LLMContextBundle`, `SymbolCard`, `PriceSnapshot`, `PortfolioContext`, `PortfolioSummary`,
`RecentDecision`, `DataQualitySection`, `OutputContract`)은 이미 정의돼 있다. 이번 단계는 이
계약을 채우는 조립 로직만 신설한다. 소비 소스는 기존 도메인 서비스·리포지토리를 읽기 전용으로
재사용한다(가격 `PriceBarRepository.list_recent` + `PriceFeatureBuilder`, 포트폴리오
`PortfolioService` 요약, decision-log `DecisionLogRepository`, 자산 `AssetRepository`).

뉴스·시그널은 계약(`SymbolCard.recent_news`, `SymbolCard.signals`)에는 존재하나 첫 구현에서는
배선하지 않고 빈 리스트 + data_quality 경고로 남긴다(Core slice, 사용자 확인). 각각 trust/severity
매핑과 별도 조회가 붙어 표면이 커지므로 6.5 후속으로 분리한다.

## 2. 범위

포함:

- 기존 도메인 `app/domains/llm_context/`에 `context_builder.py`(ContextBuilder 도메인 서비스) 신설.
- 사용자 기본 규칙 상수 모듈(`app/domains/llm_context/user_rules.py` 또는 동등 위치): §14 기본
  규칙 목록. UserRule 모델은 도입하지 않는다.
- 지침 §11(6단계)의 4개 메서드:
  - `build_symbol_context(user_id, symbol, market)` → `SymbolCard`
  - `build_portfolio_context(user_id)` → `PortfolioSummary | None`
  - `build_recent_decision_context(user_id, symbol)` → `list[RecentDecision]`
  - `build_context_bundle(task_type, user_id, symbols)` → `LLMContextBundle`
- `price_snapshot`: `PriceBarRepository.list_recent`로 조회한 bar에 `PriceFeatureBuilder`를
  적용하고, `close`는 최신 bar 종가로 채운다.
- `portfolio_context`(종목별)·`portfolio_summary`(전체): 기존 포트폴리오 요약 파생을 재사용한다.
- `recent_decisions`: decision-log 최근 기록을 조회해 매핑한다.
- `user_rules`: 기본 규칙 상수.
- `data_quality`: 소스 가용성으로 상태·경고를 산출한다.
- `output_contract`: §7 표준 required_fields.
- ContextBuilder 단위 테스트(`db` 세션 fixture 기반, 외부 API 없이).

비포함(후속 단계):

- 뉴스·시그널 배선(`recent_news`·`signals`) — 6.5 후속. 이번 단계는 빈 리스트 + data_quality
  경고(Decision AA).
- `LLMContextBundle` 영속·`input_context_json` 저장 — 7단계 `llm_analysis`.
- route 노출 — 지침 §19 "route는 마지막". 이번 단계는 도메인 서비스까지.
- DB migration — 스키마 변경 없음. 단일 alembic head `c3d4e5f60058` 유지.
- `PortfolioFeatureBuilder`·`NewsFeatureBuilder` 신설(5단계 Decision S에서 이미 유보).
- LLM 트리거 정책·이벤트 기반 자동 호출(§15).

## 3. 구성 요소

### 3.1 기본 규칙 상수 (`app/domains/llm_context/user_rules.py`)

| 심볼 | 타입 | 설명 |
| --- | --- | --- |
| `DEFAULT_USER_RULES` | `list[str]` | §14 기본 사용자 규칙 목록. config/seed 대체 상수 |

### 3.2 `ContextBuilder` (`app/domains/llm_context/context_builder.py`)

생성자는 `Session`(또는 필요한 리포지토리·서비스)을 주입받아 소스 접근을 구성한다. 모든 메서드는
읽기 전용이며 소스가 비어도 예외를 던지지 않고 빈 값·`None`·data_quality 경고로 degrade한다.

| 시그니처 | 책임 |
| --- | --- |
| `build_symbol_context(user_id, symbol, market) -> SymbolCard` | 자산 조회 → 가격 bar 조회 → `PriceFeatureBuilder`로 `PriceSnapshot`(close=최신 종가) → 종목별 `portfolio_context`(보유 시) → `recent_news=[]`·`signals=[]`(후속). display_name은 자산 메타에서 |
| `build_portfolio_context(user_id) -> PortfolioSummary \| None` | 사용자 포트폴리오 요약을 재사용해 `cash_ratio`·`top_holding_weight`·`concentration_risk`로 매핑. 포트폴리오 부재 시 `None` |
| `build_recent_decision_context(user_id, symbol) -> list[RecentDecision]` | 해당 symbol의 최근 decision-log N건 조회 → `RecentDecision`(symbol·decision_type·reason·created_at) 매핑 |
| `build_context_bundle(task_type, user_id, symbols) -> LLMContextBundle` | symbol마다 `build_symbol_context` 조립 + `build_portfolio_context` + symbol별 `build_recent_decision_context` 합류 + `user_rules`(상수) + `data_quality` 산출 + `output_contract` + `as_of`(현재) + `user_intent`(task_type 기본값). Pydantic 검증 통과 보장 |

### 3.3 `data_quality` 산출

| 필드 | 규칙(초기) |
| --- | --- |
| `price_data_status` | bar가 충분하면 `valid`, 일부만 있으면 `partial`, 없으면 `missing` |
| `news_data_status` | 이번 단계 미배선 → `missing`, warning에 사유 표기(Decision AA) |
| `portfolio_data_status` | 포트폴리오·포지션 존재 시 `valid`, 부재 시 `missing` |
| `warnings` | 위 missing/partial 사유 문자열 목록 |

## 4. Decisions

- **X. 기존 llm_context 도메인에 서비스만 추가**: 신규 도메인을 만들지 않고
  `app/domains/llm_context/`(1단계 계약 위치)에 `context_builder.py`와 규칙 상수를 더한다. 지침
  매핑 "Context Builder → domains/llm_context/(신규)"를 따른다.
- **Y. 소스 재사용·읽기 전용**: 가격·포트폴리오·decision-log·자산은 기존 리포지토리/서비스를 읽기
  전용으로 재사용한다. 기존 파일은 수정하지 않는다(신규 파일만). 포트폴리오 파생(weight·
  cash_ratio·concentration)은 이미 시세를 반영하는 기존 요약을 재사용하고 재계산하지 않는다.
- **Z. 미영속·route 미노출**: 번들을 저장하거나 route로 노출하지 않는다. 영속은 7단계
  `llm_analysis`, route는 이후 단계. 마이그레이션 미추가, 단일 head `c3d4e5f60058` 유지.
- **AA. 뉴스·시그널 후속 분리(Core slice)**: `recent_news`·`signals`는 첫 구현에서 빈 리스트로
  두고 data_quality(`news_data_status=missing`)와 warning으로 부재를 명시한다. 배선은 6.5 후속.
  번들은 계약상 유효하게 유지된다.
- **BB. user_rules 상수·UserRule 모델 미도입**: §14 기본 규칙을 모듈 상수로 둔다. `UserRule` 모델·
  마이그레이션은 규칙 편집 요구가 생기는 시점으로 유보(YAGNI).
- **CC. output_contract·user_intent 기본값**: `output_contract.required_fields`는 §7 표준 필드를
  쓰고, `user_intent`는 task_type별 기본 문구로 채운다. v0.1은 task_type과 무관하게 동일 계약을
  써도 무방하며, 세분화는 7단계 LLM Gateway에서 확정한다.
- **DD. Graceful degradation**: 자산 미존재·bar 부족·포트폴리오 부재 등 모든 소스 결손은 예외 없이
  `None`·빈 값·data_quality 경고로 표현한다. LLM이 데이터 부족을 모른 채 확신하지 않도록 한다(§13).

## 5. 마이그레이션

없음. 스키마 변경이 없다(Decision Z). alembic 단일 head `c3d4e5f60058` 유지.

## 6. 테스트

- `build_context_bundle`: 가격·포트폴리오·decision-log가 준비된 상태에서 `LLMContextBundle`이
  Pydantic 검증을 통과하고 필수 필드를 빠뜨리지 않는다(§12 "ContextBuilder가 필요한 필드를
  빠뜨리지 않는다").
- `price_snapshot`: bar가 충분하면 피처·close가 채워지고, bar가 없으면 `price_data_status=missing`
  + close/피처 `None`.
- `portfolio_context`: 보유 종목이면 holding·weight·avg_buy_price·unrealized_return이 채워지고,
  미보유면 `None`.
- `recent_decisions`: 해당 symbol의 최근 기록이 매핑되고, 없으면 빈 리스트.
- `data_quality`: 뉴스 미배선이 `news_data_status=missing` + warning으로 표기된다.
- 소스 결손: 자산·bar·포트폴리오 부재 시 예외 없이 degrade한다.
- CI 3종(ruff + mypy + pytest) 통과. 신규 타입 주석 완전화(mypy).

## 7. ADR 판단

불필요. 1단계에서 합의한 계약을 채우는 통상 조립 작업이며, 미영속·projection 네이밍·순수/부수효과
분리 등 기존 결정의 연장선이다. 뉴스·시그널 배선(6.5), LLM 트리거 정책(§15), UserRule 모델화는
필요가 구체화되는 시점에 각각 별도로 판단한다.
