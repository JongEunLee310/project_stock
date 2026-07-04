# 078 · 뉴스 파이프라인 완성 — 신뢰도 컬럼·LLM 게이트웨이 수렴

Status: Draft
작성: Claude Code (orchestrator)
관련: BE #205(신뢰도 컬럼), BE #206(게이트웨이 수렴), Epic BE #141, PR #201 리뷰 S2 후속.
지침 근거: `docs/knowledge/llm-data-pipeline.md` §5.4(신뢰도 컬럼), §18(게이트웨이 단일 진입점).

---

## 1. 배경

뉴스 파이프라인에 두 가지 잔여 작업이 남아 있다. 하나는 데이터 파이프라인 지침 §5.4의
마지막 미충족 필드이고, 다른 하나는 PR #201 로컬 리뷰 S2에서 도출된 후속이다.

첫째, `NewsItem`에 신뢰도·중복 방지를 위한 메타데이터 컬럼이 없다. `ContextBuilder`는
`_DEFAULT_NEWS_TRUST_LEVEL`을 하드코딩해 사용 중이며, 출처 다양화 시점에 출처별 신뢰도
정책을 소급 적용할 수 없다. §5.4는 `trust_level`·`content_hash` 보관을 요구한다.

둘째, `NewsAnalysisService`·`ThesisAnalysisService`가 `LLMClient`를 직접 주입받아
메시지를 조립하고 LLM을 호출한다. 이 경로는 `LLMGateway`가 제공하는 timeout·
PrivacyGate·라우팅·실행 메타를 받지 못하며, §18이 요구하는 "게이트웨이를 단일 진입점으로"
원칙에 어긋난다.

두 작업은 서로 독립적이므로 순차 구현(Part A → Part B)으로 한 PR에 동봉한다.

## 2. 범위

### Part A — `NewsItem` 메타데이터 컬럼 (BE #205)

포함:

- `app/domains/news/model.py` — `trust_level`·`content_hash` 컬럼 추가.
- alembic migration 1건 (수기 작성, `c3d4e5f60058` 기반).
- `app/domains/news/schema.py` — `NewsItemCreate`·`NewsItemResponse` 필드 반영.
- `app/domains/llm_context/context_builder.py` — `_recent_news_item_from_model` fallback 변경.

비포함:

- `trust_level`·`content_hash` 값 채움(backfill).
- 기존 뉴스 수집·파싱 로직 변경.

### Part B — LLM 게이트웨이 수렴 (BE #206)

포함:

- `app/adapters/llm/privacy.py` — `NewsSummarySnapshot`·`ThesisConflictSnapshot` 추가.
- `app/adapters/llm/prompts/news_summary.py`·`thesis_conflict.py` — 시스템 프롬프트 빌더로 재편.
- `app/domains/news/service.py` — `NewsAnalysisService` 주입 전환.
- `app/domains/theses/conflict_service.py` — `ThesisAnalysisService` 주입 전환.
- `app/domains/analysis/service.py` — `WatchlistAnalysisService` 주입 전환.
- `app/worker/jobs/analysis.py` — `get_llm_client()` 제거·`get_llm_gateway()` 적용.
- 영향받는 테스트의 mock 조립 방식 갱신.

비포함:

- `app/adapters/llm/gateway.py`·`router.py`·`base.py` 변경.
- `app/domains/llm_analysis/` 변경.
- 프롬프트 지시문 내용 변경.
- 실행 메타(provider·model_name) 영속화.

## 3. 구성 요소

### 3.1 `NewsItem` 모델 확장 (`app/domains/news/model.py`)

| 컬럼 | 타입 | 제약 | 책임 |
|---|---|---|---|
| `trust_level` | `String(20)` | nullable | 출처별 신뢰도 레이블 보관 |
| `content_hash` | `String(64)` | nullable | sha256 hex 기준 본문 지문 보관 |

### 3.2 스키마 반영 (`app/domains/news/schema.py`)

| 클래스 | 변경 |
|---|---|
| `NewsItemCreate` | `trust_level: str \| None = None`, `content_hash: str \| None = None` 추가 |
| `NewsItemResponse` | 동일 |

### 3.3 `ContextBuilder` fallback (`app/domains/llm_context/context_builder.py`)

| 함수 | 시그니처 | 책임 변경 |
|---|---|---|
| `_recent_news_item_from_model` | 변경 없음 | `news_item.trust_level`이 존재하면 저장값 사용, 없으면 `_DEFAULT_NEWS_TRUST_LEVEL` fallback |

### 3.4 CloudSafePayload 스냅샷 (`app/adapters/llm/privacy.py`)

| 클래스 | 상위 타입 | 필드 | sensitivity |
|---|---|---|---|
| `NewsSummarySnapshot` | `CloudSafePayload` | `title: str`, `body: str` | `PUBLIC` |
| `ThesisConflictSnapshot` | `CloudSafePayload` | `thesis_summary: str`, `invalidation_conditions: str`, `news_summary: str`, `news_positive_factors: list[str]`, `news_negative_factors: list[str]` | `AGGREGATED` |

### 3.5 시스템 프롬프트 빌더

| 파일 | 함수 | 책임 |
|---|---|---|
| `app/adapters/llm/prompts/news_summary.py` | `build_news_summary_system_prompt() -> str` | 기존 지시문 + JSON Schema를 담은 시스템 프롬프트 반환 |
| `app/adapters/llm/prompts/thesis_conflict.py` | `build_thesis_conflict_system_prompt() -> str` | 기존 지시문 + JSON Schema를 담은 시스템 프롬프트 반환 |

기존 `build_news_summary_messages`·`build_thesis_conflict_messages`는 제거한다.
`LLMGateway.complete_json`이 스냅샷 JSON을 사용자 메시지로 조립하므로 호출자가
메시지 리스트를 직접 구성할 필요가 없다.

### 3.6 서비스 시그니처

| 클래스 | 파일 | 시그니처 (변경 후) | 책임 요약 |
|---|---|---|---|
| `NewsAnalysisService` | `app/domains/news/service.py` | `__init__(self, db, gateway: LLMGateway)` | 뉴스 요약 분석 요청을 게이트웨이로 위임 |
| `ThesisAnalysisService` | `app/domains/theses/conflict_service.py` | `__init__(self, db, gateway: LLMGateway)` | 논지 충돌 분석 요청을 게이트웨이로 위임 |
| `WatchlistAnalysisService` | `app/domains/analysis/service.py` | `__init__(self, db, gateway: LLMGateway, news_adapter)` | 두 하위 서비스에 게이트웨이를 주입해 생성 |

`completion.output`은 기존과 동일하게 `model_validate`에 연결한다.

### 3.7 워커 잡 (`app/worker/jobs/analysis.py`)

| 변경 | 내용 |
|---|---|
| `get_llm_client()` 제거 | 잡 함수에서 `LLMClient` 직접 취득 불필요 |
| `get_llm_gateway()` 적용 | `WatchlistAnalysisService` 생성 시 게이트웨이 주입 |

## 4. Decisions

- **Decision AAA — `trust_level`(String(20))·`content_hash`(String(64))를 nullable로 추가하고,
  값 채움 정책은 이 시점에 정하지 않는다.** 현재 rss 단일 계열 구조에서는 url로 dedup이
  충분하고, 출처별 신뢰도 매핑은 출처가 다양화될 때 정책과 함께 결정하는 것이 맞다. 컬럼만
  지금 추가하면 이후 migration을 한 번으로 줄일 수 있다.

- **Decision BBB — `ContextBuilder`는 `news_item.trust_level` 저장값을 우선 사용하고,
  없으면 `_DEFAULT_NEWS_TRUST_LEVEL`로 fallback한다.** 소급 backfill은 하지 않는다.
  컬럼 추가 이후 수집된 뉴스부터 저장값이 채워지며, 그 이전 레코드는 기존 상수를 그대로
  사용하므로 동작이 보존된다.

- **Decision CCC — 두 경로의 게이트웨이 수렴은 전용 CloudSafePayload 스냅샷과 시스템
  프롬프트 빌더 재편으로 구현한다.** `privacy.py`에 `NewsSummarySnapshot`·
  `ThesisConflictSnapshot`을 추가하고, 프롬프트 파일은 메시지 리스트 조립자에서 시스템
  프롬프트 반환 함수(`build_*_system_prompt()`)로 교체한다. 사용자 메시지 형식이 산문
  조립에서 스냅샷 JSON으로 바뀌는 것은 허용한다(게이트웨이 표준 형식). 기각 대안: 게이트웨이에
  메시지 리스트 오버로드 추가 — 게이트웨이의 "ContextBundle(CloudSafePayload)만 입력"
  원칙(§18)을 깨므로 기각한다.

- **Decision DDD — sensitivity 분류는 `NewsSummarySnapshot`을 PUBLIC, `ThesisConflictSnapshot`을
  AGGREGATED로 한다.** `NewsSummarySnapshot`은 공개 기사 제목·본문만 담는다. `ThesisConflictSnapshot`은
  사용자 작성 투자 논지 텍스트를 담지만 계좌·수량·금액 등 개인 재무 데이터는 포함하지 않으며,
  현재도 직접 호출 경로로 cloud에 전송 중이므로 동작을 보존하는 분류다. PrivacyGate의 cloud
  허용 기준은 AGGREGATED·PUBLIC이므로 두 스냅샷 모두 cloud 라우팅을 통과한다.

## 5. 마이그레이션

Part A에서 alembic migration 1건을 수기 작성한다. 기준 head는 `c3d4e5f60058`이며, 컬럼
2개(`trust_level`·`content_hash`)를 nullable로 추가하는 `op.add_column` 2건과 downgrade
`op.drop_column` 2건으로 구성된다. 완료 후 `uv run alembic heads`로 단일 head 유지를 확인한다.

Part B에는 스키마 변경이 없으므로 migration이 불필요하다.

## 6. 테스트

- **ContextBuilder fallback 회귀** — `trust_level=None`인 `NewsItem` fixture로
  `_recent_news_item_from_model`을 호출하면 `_DEFAULT_NEWS_TRUST_LEVEL`이 적용되는지,
  `trust_level="high"`인 경우 저장값이 그대로 반환되는지 각각 검증한다.
- **게이트웨이 수렴 경로** — `MockLLMClient`로 조립한 실제 `LLMGateway`(또는 stub
  게이트웨이)를 주입한 `NewsAnalysisService`·`ThesisAnalysisService`에서 요약·충돌 분석
  결과가 기존과 동일하게 저장되는지 검증한다.
- **기존 테스트 전부 통과** — `MockLLMClient` 직접 주입 테스트는 mock 게이트웨이 조립로
  갱신한다.

## 7. ADR 판단

불필요. 이 설계는 ADR-009(CloudSafe DTO 경계)·§18(게이트웨이 단일 진입점) 등 기존
결정의 적용이며 새로운 아키텍처 방향을 선택하는 것이 아니다. 단, Decision DDD의 sensitivity
분류는 이 설계 문서에 명시적으로 남긴다(§4 참조).

## 8. Failure Record 판단

불필요. 이번 작업은 결함 마감이 아니라 계획된 스키마 완성과 경로 수렴이다.
