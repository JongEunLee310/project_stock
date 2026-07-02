# 067 · LLM 데이터 파이프라인 1단계 — 데이터 계약 정의 (Data Contracts)

Status: Draft
작성: Claude Code (orchestrator)
관련: Epic BE #174(LLM 사전 데이터 수집·가공 파이프라인 v0.1), Milestone 데이터 수집
파이프라인 — 백엔드(#5). 기준 문서 `docs/knowledge/llm-data-pipeline.md`(11절 1단계, PR #173).
LLM 하이브리드 아키텍처(Epic #141)의 데이터 계약 선행.

## 1. 배경

지침 11절은 파이프라인을 데이터 계약 정의부터 시작한다. 서비스·정규화·피처·ContextBuilder를
붙이기 전에 Pydantic Schema와 SQLAlchemy Model의 계약을 먼저 확정해, 이후 단계가 흔들리지 않는
기준을 만든다. 본 설계는 **계약 정의만** 다룬다. 수집·정규화·검증·피처·ContextBuilder·Gateway
로직은 2~7단계에서 각각 붙인다.

지침 1단계 대상 9종 중 다수는 이미 존재한다. 중복 정의를 피하기 위해 기존 모델에 매핑하고,
실제 신규 정의 대상만 추린다.

| 지침 명칭 | 현재 상태 | 본 단계 처리 |
| --- | --- | --- |
| Watchlist | 존재(`domains/watchlists`) | 재사용, 신규 없음 |
| PortfolioPosition | 존재(`domains/portfolios`) | 재사용, 신규 없음 |
| PriceDaily | 존재(`domains/prices`, `prices` 테이블) | 재사용, 신규 없음 |
| NewsArticle | 존재(`domains/news`, `news_items`/`NewsItem`) | 재사용(명칭만 대응), 신규 없음 |
| DecisionLog | 존재(`domains/decision_logs`) | 재사용, `suggested_action` 어휘 정합 |
| RawProviderResponse | 부재 | **신규(경계 projection + `ProcessingStatus`)** |
| LLMContextBundle | 부재 | **신규(Pydantic projection 계층)** |
| LLMAnalysisRun | 부재 | **신규(SQLAlchemy Model)** |
| LLMAnalysisResult | 부재 | **신규(Pydantic 출력 스키마)** |

기존 LLM 어댑터(`app/adapters/llm/`, Epic #141)에는 이미 `LLMTaskType`·`LLMRequest`/
`LLMResponse`·`RiskLevel`·`LLMGateway.complete_json`·`CloudSafePayload`가 있다. 본 단계의 계약은
이들을 **대체하지 않고 재사용·정합**한다. 어댑터는 1회성 요청/응답 전송 계약이고, 본 단계의
`LLMAnalysisRun`은 그 실행을 **영속화**하는 별도 계약이다.

## 2. 범위

포함(계약 정의만):

- `LLMContextBundle` Pydantic projection 계층(지침 7절) + 데이터 품질/출력 계약 enum.
- `LLMAnalysisResult` Pydantic 출력 스키마(지침 8절) + `SuggestedAction` enum.
- `LLMAnalysisRun` SQLAlchemy Model + 마이그레이션(지침 3.5·16절).
- `RawProviderResponse` 경계 Pydantic projection + `ProcessingStatus` enum(지침 3.3·6.2).
- 각 계약의 Pydantic validation 테스트(외부 API·DB 세션 불필요).

비포함(후속 단계):

- Raw 저장 구조 보강(`processing_status` 컬럼 적용) — 2단계.
- Normalizer / Validator 로직 — 3·4단계.
- Feature Builder — 5단계.
- ContextBuilder 조립 로직(`build_context_bundle` 등) — 6단계. 본 단계는 그 **산출물 타입**만
  정의한다.
- LLM Gateway 저장 연결(`LLMAnalysisRun` 실제 write) — 7단계. 본 단계는 **스키마**만 만든다.
- route·API 노출(`endpoints/llm_analysis.py`) — 후속.

## 3. 신규 도메인 배치

지침 9절(도메인 응집형 레이아웃)을 따른다. 용어: 경계·파생 뷰 Pydantic 타입은 프로젝트 관례상
"DTO" 대신 "projection"으로 부른다(#132, ADR-009). HTTP 요청/응답은 `schema`, `LLMRequest`
내용은 `payload`로 이미 쓰여 충돌하기 때문이다.

```
app/domains/
  llm_context/                 # 신규 — ContextBundle 계약
    schema.py                  # LLMContextBundle + 중첩 projection + enum
  llm_analysis/                # 신규 — 분석 실행/결과 계약
    model.py                   # LLMAnalysisRun (테이블)
    schema.py                  # LLMAnalysisRun I/O 스키마 + LLMAnalysisResult 출력 스키마
  ingestion/                   # 신규(경량) — 수집 경계 계약
    schema.py                  # RawProviderResponse + ProcessingStatus
```

`ingestion/`은 특정 provider에 묶이지 않는 공통 경계 계약만 담는다. 기존 `raw_prices`·
`raw_news`는 각자 원본 테이블(raw store)로 유지하고, 본 단계에서 스키마를 바꾸지 않는다.

## 4. RawProviderResponse — 경계 projection (`domains/ingestion/schema.py`)

지침 3.2는 원본/정규화 분리를, 3.3은 외부 응답 → 내부 표준 projection 변환을 요구한다. 현재 원본
저장은 이미 `raw_prices`(payload_hash dedup)·`raw_news_events`(url dedup)로 구현돼 있어, **통합
원본 테이블을 새로 만들지 않는다**(§9 Decision A). 대신 두 수집 경로가 공통으로 emit할 수 있는
**표준 경계 projection**으로 계약을 세운다.

`RawProviderResponse` (Pydantic, 저장 아님):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| provider | str | 공급자 식별(예: `yfinance`, `rss`) |
| data_type | `RawDataType` | `price` \| `news`(초기 2종) |
| symbol | str \| None | 귀속 종목(뉴스 독립 수집 시 nullable) |
| market | str \| None | 귀속 시장 |
| payload | dict[str, Any] | 외부 응답 원본 |
| payload_hash | str | 중복 판별 해시 |
| fetched_at | datetime | 수집 시각(tz-aware) |
| processing_status | `ProcessingStatus` | 기본 `fetched` |

`ProcessingStatus` enum(지침 6.2): `fetched` \| `normalized` \| `failed` \| `skipped_duplicate`.
`RawDataType` enum: `price` \| `news`.

> 이 projection은 2단계에서 기존 raw 테이블에 `processing_status` 컬럼을 붙이고 수집 서비스가 emit하도록
> 연결한다. 본 단계는 타입 정의와 validation까지만 한다.

## 5. LLMContextBundle — 입력 projection 계층 (`domains/llm_context/schema.py`)

지침 7절 예시 JSON을 Pydantic 계약으로 옮긴다. 모든 중첩은 BaseModel로 강타입화한다.

`LLMContextBundle`:

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| task_type | `LLMTaskType` | 기존 enum 재사용(§9 Decision C) |
| as_of | datetime | 스냅샷 기준 시각(tz-aware) |
| user_intent | str | 사용자 의도 요약 |
| symbols | list[str] | 대상 심볼 |
| data_quality | `DataQualitySection` | 필수(지침 13절) |
| symbol_cards | list[`SymbolCard`] | 종목별 카드 |
| portfolio_summary | `PortfolioSummary` \| None | 포트폴리오 요약 |
| user_rules | list[str] | 사용자 규칙(지침 14절) |
| recent_decisions | list[`RecentDecision`] | 과거 판단 요약 |
| output_contract | `OutputContract` | 출력 요구 계약 |

중첩 projection(필드는 지침 7절 예시 기준):

- `DataQualitySection`: price_data_status·news_data_status·portfolio_data_status(`DataQualityStatus`),
  warnings(list[str]).
- `SymbolCard`: symbol·market·display_name, price_snapshot(`PriceSnapshot`),
  portfolio_context(`PortfolioContext` \| None), recent_news(list[`RecentNewsItem`]),
  signals(list[`SignalItem`]).
- `PriceSnapshot`: close, return_1d/5d/20d, drawdown_from_52w_high, volume_vs_20d_avg(모두 float \| None).
- `PortfolioContext`: holding(bool), weight, avg_buy_price, unrealized_return.
- `RecentNewsItem`: title, summary, source, published_at, trust_level.
- `SignalItem`: type, severity, reason.
- `PortfolioSummary`: cash_ratio, top_holding_weight, concentration_risk.
- `RecentDecision`: symbol, decision_type, reason, created_at.
- `OutputContract`: format(기본 `json`), required_fields(list[str]).

`DataQualityStatus` enum(지침 13절): `valid` \| `invalid` \| `stale` \| `partial` \| `duplicate` \|
`low_trust` \| `missing`.

## 6. LLMAnalysisResult — 출력 스키마 (`domains/llm_analysis/schema.py`)

지침 8절. LLM이 반환할 구조화 출력 계약이며, 자유 텍스트를 금지한다.

`LLMAnalysisResult` (Pydantic):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| summary | str | 상황 요약 |
| risk_level | `RiskLevel` | 기존 enum 재사용(§9 Decision C) |
| suggested_action | `SuggestedAction` | 명령형 금지 enum |
| reasons | list[str] | 근거 |
| watch_points | list[str] | 관찰 포인트 |
| counter_arguments | list[str] | 반대 시나리오 |
| data_limitations | list[str] | 데이터 한계 |
| confidence | float | 0.0~1.0 |

`SuggestedAction` enum(지침 8절): `buy_watch` \| `hold` \| `trim_watch` \| `avoid` \|
`need_more_data`. `buy`/`sell`/`strong_buy`/`strong_sell` 등 명령형 값은 정의하지 않는다(지침
17절). DecisionLog의 `decision_type` 어휘와 정합한다(§9 Decision D).

## 7. LLMAnalysisRun — 영속 모델 (`domains/llm_analysis/model.py`)

지침 3.5·16절. LLM 입력·출력을 재현 가능하게 저장한다. `input_context_json`(=ContextBundle)을
반드시 함께 저장한다(지침 17절 금지: 결과만 저장 금지).

`LLMAnalysisRun` (테이블 `llm_analysis_runs`, `Base` + `TimestampMixin`):

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| id | int PK | |
| user_id | int FK(`users.id`) | |
| task_type | str | `LLMTaskType` 값 저장 |
| related_symbols | JSON(list[str]) | 대상 심볼 |
| input_context_json | JSON | `LLMContextBundle` 직렬화(필수) |
| output_json | JSON \| None | `LLMAnalysisResult` 직렬화 |
| status | str | `RunStatus`(pending/succeeded/failed) |
| model_name | str \| None | 사용 모델 |
| prompt_version | str \| None | 프롬프트 버전 |
| provider | str \| None | cloud/local(라우팅 결과) |
| related_decision_log_id | int \| None FK(`decision_logs.id`) | 연결 판단 |
| error_message | str \| None | 실패 사유 |

`RunStatus` enum: `pending` \| `succeeded` \| `failed`. created_at/updated_at은 `TimestampMixin`.

`LLMAnalysisResult`를 별도 테이블로 두지 않고 `output_json`에 저장한다(§9 Decision B). **DB 스키마
신설 → 마이그레이션 필요.**

## 8. 테스트

계약 단위 테스트(외부 API·DB 세션 불필요, 지침 12절):

- `LLMContextBundle`이 지침 7절 예시 JSON을 통과시키고, `data_quality` 누락 시 validation 실패.
- 잘못된 `DataQualityStatus`/`SuggestedAction` 값은 거부.
- `LLMAnalysisResult`가 지침 8절 예시를 통과, `confidence` 범위(0~1) 밖은 거부, 명령형 action 거부.
- `RawProviderResponse`가 `ProcessingStatus` 기본값 `fetched`로 생성.
- `LLMAnalysisRun` 모델이 `input_context_json` 없이 생성 불가(비null 계약) — 모델 레벨 테스트.
- 마이그레이션 up/down이 깨지지 않음(스키마 회귀).
- CI 3종(ruff + mypy + pytest) 통과. 신규 모델은 타입 주석 완전화(mypy `no-untyped-def` 회피).

## 9. Decisions

- **A. 통합 원본 테이블 미신설**: 지침의 `raw_provider_responses` 통합 테이블 대신 기존
  `raw_prices`·`raw_news_events`를 원본 저장소로 유지한다. 두 테이블이 이미 원본/정규화 분리와
  dedup을 충족하며, 통합 테이블 신설은 중복·마이그레이션 부담만 늘린다(YAGNI). `RawProviderResponse`는
  두 경로가 공유하는 경계 projection으로만 둔다. 통합 저장은 공급자가 늘어날 때 재검토한다.
- **B. LLMAnalysisResult 테이블 미분리**: 출력은 `LLMAnalysisRun.output_json`(JSONB)에 저장하고
  별도 결과 테이블을 두지 않는다. 결과 단독 질의 요구가 생기면 승격한다(지침 16절 초기 JSONB 충분).
- **C. 기존 LLM enum 재사용**: `task_type`·`risk_level`은 `app/adapters/llm/types.py`의
  `LLMTaskType`·`RiskLevel`을 재사용해 어댑터(Epic #141)와 어휘를 통일한다. 지침 예시의
  `symbol_risk_review` 등 신규 task가 필요하면 `LLMTaskType`에 값을 추가한다(별도 enum 신설 금지).
- **D. suggested_action ↔ decision_type 정합**: `SuggestedAction`은 DecisionLog `decision_type`
  어휘(watch/buy_watch/hold/trim_watch/avoid/need_more_data)와 정합하되, 출력 계약에는 명령형
  값을 넣지 않는다.

## 10. ADR 판단

경계선. 계약 정의 자체는 기존 도메인 응집형 패턴을 따르는 통상 작업이라 ADR 불필요다. 다만
Decision A(통합 원본 테이블을 두지 않고 경계 projection으로 대체)와 Decision C(어댑터 enum 재사용)는 지침
문서의 문언과 다른 방향이므로, 개발자 리뷰에서 이견이 있으면 ADR로 승격한다. LLM 어댑터(Epic
#141)와 본 파이프라인의 경계·소유권 정리가 커지면 별도 ADR로 다룬다.
