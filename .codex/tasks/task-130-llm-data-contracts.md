# Codex Handoff Task

## Source Issue

BE #175(LLM 파이프라인 1단계 · 데이터 계약 정의). 상위 Epic #174. 설계
`docs/designs/067-llm-data-contracts.md`. 기준 문서 `docs/knowledge/llm-data-pipeline.md`(11절
1단계). Milestone: 데이터 수집 파이프라인 — 백엔드(#5).

## Task Summary

LLM 사전 데이터 파이프라인의 신규 데이터 계약을 **정의만** 한다. 수집·정규화·검증·피처·
ContextBuilder·Gateway 로직은 후속 단계(2~7단계)이며 본 task 범위가 아니다. 신규 대상은
`RawProviderResponse`(경계 projection), `LLMContextBundle`(입력 projection 계층),
`LLMAnalysisResult`(출력 스키마), `LLMAnalysisRun`(영속 모델) 4종이다. 기존 모델
(Watchlist/PortfolioPosition/PriceDaily/NewsItem/DecisionLog)은 재사용하며 신규 정의하지 않는다.

## Goal

완료 시 참이어야 할 것:

- `app/domains/ingestion/schema.py`에 `RawProviderResponse` Pydantic 모델과 `ProcessingStatus`·
  `RawDataType` enum이 있고, `ProcessingStatus` 기본값이 `fetched`로 인스턴스가 생성된다.
- `app/domains/llm_context/schema.py`에 `LLMContextBundle` + 중첩 projection + `DataQualityStatus`
  enum이 있고, 지침 7절 예시 JSON이 validation을 통과한다. `data_quality` 누락 시 실패한다.
- `app/domains/llm_analysis/schema.py`에 `LLMAnalysisResult`(지침 8절) + `SuggestedAction`·
  `RunStatus` enum이 있고, 지침 8절 예시가 통과한다. `confidence` 범위(0.0~1.0) 밖과 명령형
  action 값은 거부된다.
- `app/domains/llm_analysis/model.py`에 `LLMAnalysisRun` 테이블(`llm_analysis_runs`)이 있고,
  `input_context_json`이 non-null 계약이다. alembic 마이그레이션이 up/down 모두 동작한다.
- 신규 모델이 `alembic/env.py`에 import 등록되어 autogenerate 대상에 포함된다.
- 위 계약의 단위 테스트가 외부 API·DB 세션 없이 통과한다.
- ruff·mypy·pytest 전부 통과한다.

## Background

- **Pydantic 관례**: v2. `app/domains/raw_prices/schema.py` 참고 — `BaseModel`,
  `Field(max_length=...)`, 응답용은 `model_config = {"from_attributes": True}`. tz-aware
  datetime은 `app/core/schema.py`의 `UtcDatetime`을 쓴다.
- **enum 관례**: `str, Enum` 서브클래스로 도메인 `types.py` 또는 `schema.py`에 둔다
  (`app/domains/decision_logs/types.py` 참고).
- **모델 관례**: `app/db/base.py`의 `Base` + `TimestampMixin`(created_at/updated_at 제공).
  JSON 컬럼은 `sqlalchemy.JSON`, FK는 `ForeignKey("...")`. `app/domains/decision_logs/model.py`가
  JSON·FK·enum 값 저장의 좋은 예시다.
- **기존 LLM 어댑터 재사용(Decision C)**: `app/adapters/llm/types.py`에 `LLMTaskType`
  (NEWS_SUMMARY/THESIS_CONFLICT/PORTFOLIO_BRIEFING/DASHBOARD_BRIEFING/WATCHLIST_NOTE/
  TAG_SENTIMENT/AGENT)와 `RiskLevel`(LOW/MEDIUM/HIGH)이 이미 있다. `task_type`·`risk_level`은
  이 enum들을 **재사용**한다(병렬 enum 신설 금지). 값들은 대문자다 — 그대로 쓴다. 지침 예시의
  `symbol_risk_review` 같은 신규 task가 실제로 필요해지면 `LLMTaskType`에 값을 **추가**한다(본
  task에서는 기존 값으로 충분, 임의 추가하지 말 것).
- **SuggestedAction은 독립 enum(중요)**: 지침 8·17절은 LLM 출력에 `buy`/`sell` 등 명령형
  action을 금지한다. 반면 기존 `app/domains/decision_logs/types.py`의 `DecisionType`은
  대문자에 `BUY`/`SELL`을 포함하는 **다른 개념**(사용자가 기록한 판단 로그)이다. 따라서
  `SuggestedAction`은 `DecisionType`을 재사용·미러링하지 **않고** 별도 신규 enum으로 만든다.
  값: `buy_watch`·`hold`·`trim_watch`·`avoid`·`need_more_data`(소문자, 지침 8절). 명령형 값
  금지.
- **원본 저장 미변경(Decision A)**: 원본은 이미 `raw_prices`(payload_hash dedup)·
  `raw_news_events`(url dedup)에 저장된다. 본 task는 이 테이블·저장 로직을 건드리지 않는다.
  `RawProviderResponse`는 두 수집 경로가 공통으로 emit할 **경계 projection 타입**(테이블 아님)
  으로만 정의한다. 통합 원본 테이블은 만들지 않는다.
- **결과 테이블 미분리(Decision B)**: `LLMAnalysisResult`는 Pydantic 출력 스키마로만 두고,
  실제 값은 `LLMAnalysisRun.output_json`(JSON)에 저장한다. 결과 전용 테이블은 만들지 않는다.
- **모델 등록**: `alembic/env.py`는 각 모델을 명시적으로 import해 autogenerate에 넣는다. 신규
  `LLMAnalysisRun`도 `import app.domains.llm_analysis.model  # noqa: F401` 한 줄을 추가한다.
- 마이그레이션 구조는 `docs/designs/039-db-migration-structure.md`를 따른다.

## Implementation Scope

- `app/domains/ingestion/__init__.py`(신규), `app/domains/ingestion/schema.py`(신규):
  - `ProcessingStatus(str, Enum)`: `fetched`·`normalized`·`failed`·`skipped_duplicate`.
  - `RawDataType(str, Enum)`: `price`·`news`.
  - `RawProviderResponse(BaseModel)`: provider(str), data_type(`RawDataType`), symbol(str|None),
    market(str|None), payload(dict[str, Any]), payload_hash(str), fetched_at(datetime),
    processing_status(`ProcessingStatus`, 기본 `fetched`).
- `app/domains/llm_context/__init__.py`(신규), `app/domains/llm_context/schema.py`(신규):
  - `DataQualityStatus(str, Enum)`: `valid`·`invalid`·`stale`·`partial`·`duplicate`·`low_trust`·
    `missing`.
  - 중첩 projection(설계 067 §5, 필드는 지침 7절 예시 기준): `DataQualitySection`,
    `PriceSnapshot`, `PortfolioContext`, `RecentNewsItem`, `SignalItem`, `SymbolCard`,
    `PortfolioSummary`, `RecentDecision`, `OutputContract`.
  - `LLMContextBundle(BaseModel)`: task_type(`LLMTaskType`), as_of(datetime), user_intent(str),
    symbols(list[str]), data_quality(`DataQualitySection`, 필수), symbol_cards(list[`SymbolCard`]),
    portfolio_summary(`PortfolioSummary`|None), user_rules(list[str]),
    recent_decisions(list[`RecentDecision`]), output_contract(`OutputContract`).
- `app/domains/llm_analysis/__init__.py`(신규), `app/domains/llm_analysis/schema.py`(신규):
  - `SuggestedAction(str, Enum)`: `buy_watch`·`hold`·`trim_watch`·`avoid`·`need_more_data`.
  - `RunStatus(str, Enum)`: `pending`·`succeeded`·`failed`.
  - `LLMAnalysisResult(BaseModel)`: summary(str), risk_level(`RiskLevel`),
    suggested_action(`SuggestedAction`), reasons(list[str]), watch_points(list[str]),
    counter_arguments(list[str]), data_limitations(list[str]), confidence(float, 0.0~1.0 제약).
  - `LLMAnalysisRun`의 create/response 스키마(선택) — 필요 최소만.
- `app/domains/llm_analysis/model.py`(신규): `LLMAnalysisRun(Base, TimestampMixin)` 테이블
  `llm_analysis_runs`(설계 067 §7 필드표): id PK, user_id FK(`users.id`), task_type(str),
  related_symbols(JSON), input_context_json(JSON, non-null), output_json(JSON, nullable),
  status(str), model_name(str|None), prompt_version(str|None), provider(str|None),
  related_decision_log_id(int|None FK `decision_logs.id`), error_message(str|None).
- `alembic/env.py`: `import app.domains.llm_analysis.model  # noqa: F401` 추가.
- `alembic/versions/`: `llm_analysis_runs` 신설 마이그레이션(설계 039 구조).
- 테스트(아래 Test Requirements).

## Out of Scope

- 2단계~7단계 로직: Raw 저장 구조 보강(`processing_status` 컬럼 적용), Normalizer, Validator,
  Feature Builder, ContextBuilder 조립 로직(`build_context_bundle` 등), Gateway 저장 연결.
- route·API 노출(`endpoints/llm_analysis.py` 등). 본 task는 route를 추가하지 않는다.
- 기존 `raw_prices`·`raw_news_events`·`prices`·`news_items`·`decision_logs` 스키마 변경.
- 기존 `app/adapters/llm/*` 변경(enum은 재사용만, 수정 금지).
- 사용자 규칙(UserRule) 모델, seed 데이터.

## Protected Files

`app/adapters/llm/*`, `app/domains/decision_logs/*`, `app/domains/raw_prices/*`,
`app/domains/raw_news/*`, `app/domains/prices/*`, `app/domains/news/*`는 변경하지 않는다.
`LLMTaskType`·`RiskLevel`은 재사용만 하고 수정하지 않는다. Implementation Scope 밖 파일은
`alembic/env.py`의 한 줄 import 추가를 제외하고 변경하지 않는다.

## Requirements

- 신규 계약은 순수 정의다. 수집·정규화·검증·조립·LLM 호출 로직을 넣지 않는다.
- `LLMContextBundle`은 `data_quality`를 반드시 포함한다(지침 13절, 누락 시 validation 실패).
- `LLMAnalysisResult.suggested_action`에 명령형 값(buy/sell/strong_buy/strong_sell 등)이 없다.
- `LLMAnalysisRun.input_context_json`은 non-null이다(지침 17절: 결과만 저장 금지).
- `LLMAnalysisResult`는 별도 테이블을 만들지 않는다(`output_json`에 저장, Decision B).
- 통합 원본 테이블을 만들지 않는다(Decision A). `RawProviderResponse`는 저장 모델이 아니다.
- 신규 모델은 타입 주석을 완전히 채워 mypy `no-untyped-def`를 피한다.

## Test Requirements

- `LLMContextBundle`이 지침 7절 예시 JSON을 통과한다. `data_quality` 누락 시 `ValidationError`.
- 잘못된 `DataQualityStatus`/`SuggestedAction`/`RiskLevel` 값은 거부된다.
- `LLMAnalysisResult`가 지침 8절 예시를 통과한다. `confidence`가 0~1 밖이면 거부, 명령형 action
  문자열은 거부된다.
- `RawProviderResponse`가 `processing_status` 기본값 `fetched`로 생성된다.
- `LLMAnalysisRun`이 `input_context_json` 없이 생성 불가함을 모델 레벨(또는 DB 제약)로 확인한다.
- 마이그레이션 up/down이 깨지지 않는다(스키마 회귀).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest`

## Documentation Impact

설계 `docs/designs/067-llm-data-contracts.md`가 근거다. 신규 도메인 패키지·`llm_analysis_runs`
테이블 추가는 knowledge/도메인 문서 반영 여부를 orchestrator가 리뷰 시 판단한다. Codex는 문서를
새로 쓰지 않는다.

## ADR Need

경계선. 계약 정의 자체는 통상 작업이라 불필요. Decision A(통합 원본 테이블 미신설)·C(어댑터
enum 재사용)는 지침 문언과 다른 방향이나 이미 설계 리뷰에서 합의됐다(#175/#176). 이견이 생기면
orchestrator가 ADR로 승격한다. Codex는 ADR을 작성하지 않는다.

## Failure Record Need

불필요.

## Risk Level

Low. 순수 계약 정의 + 단일 신규 테이블 마이그레이션이다. 외부 네트워크·기존 스키마 변경이 없다.
주의점은 (1) `SuggestedAction`을 `DecisionType`과 혼동하지 않기(독립 enum, 명령형 금지),
(2) `LLMTaskType`·`RiskLevel` 재사용(신설 금지), (3) `input_context_json` non-null,
(4) 신규 모델의 `alembic/env.py` 등록 누락 방지, (5) mypy 타입 완전화다.

## Expected Output

- 위 scope의 신규 3개 도메인 패키지(schema/model)·enum·마이그레이션·`alembic/env.py` 등록·테스트.
- 검증 3종(ruff·mypy·pytest) 통과 로그.
- 가정(필드 타입·기본값·제약)과 검증 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files (특히 `app/adapters/llm/*`, 기존 도메인 모델).
- Do not add routes or 2~7단계 로직.
- `SuggestedAction`은 독립 enum으로, 명령형 값 없이 정의한다.
- Report assumptions and verification results.

## Stop Conditions

- 기존 `LLMTaskType`/`RiskLevel` 값만으로 `LLMContextBundle`/`LLMAnalysisResult`를 표현할 수
  없다고 판단되면 멈추고 보고한다(enum 확장은 orchestrator 판단).
- `llm_analysis_runs` 마이그레이션이 기존 마이그레이션 체인과 충돌하면 멈추고 보고한다.
- 신규 도메인 패키지 배치가 기존 import 구조와 충돌하면 멈추고 보고한다.
