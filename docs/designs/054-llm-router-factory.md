# 054 · LLMRouter + factory 배선 + LLM_PROVIDER 설정 (task→provider 라우팅)

Status: Frozen
작성: Claude Code (orchestrator)
관련: 이슈 #134, Epic #141, ADR-007(Provider Abstraction)·ADR-008(Task Routing)

## 1. 배경

#133이 분류 enum·요청/응답 봉투·`LocalLLMProvider` stub을 도입했다. 본 작업은 그
위에서 **provider 선택을 task 인지형으로 확장**한다. ADR-008은 라우팅을 호출부 로직이
아니라 config 주도 정책으로 두고, `task_type → provider` 매핑과 `LLM_PROVIDER` 설정,
factory 배선을 #134 범위로 못박았다.

본 작업은 라우터·설정·factory 배선과 worker job 정리까지다. 라우터를 실제 진입점으로
묶는 `LLMGateway`(ADR-008이 #136으로 명시)와 PrivacyGate(#135)는 본 범위가 아니다.
라우터는 #133의 타입처럼 **도입·단위테스트만** 하고, 살아있는 소비처(gateway)는 #136이
연결한다.

## 2. 범위

포함:

- 신규 모듈 `app/adapters/llm/router.py` — `LLMRouter` + 라우팅 표(데이터 주도).
- `app/core/config.py` — `LLM_PROVIDER` 설정 신설(기존 `*_PROVIDER` Literal 패턴).
- `app/adapters/factory.py` — `get_llm_client()` 추가(`settings.LLM_PROVIDER` 기준
  transport 선택).
- `app/adapters/llm/mock.py` — worker가 쓰던 캔드 응답을 모듈 기본값으로 이전.
- `app/worker/jobs/analysis.py` — 인라인 `MockLLMClient(...)` 생성 제거 →
  `get_llm_client()` 경유.
- `.env.example` — `LLM_PROVIDER` 항목 추가(로컬 dev는 `mock`).

비포함:

- `get_llm_gateway()`·`LLMGateway`·gateway.py 조립(#136, ADR-008 Follow-up).
- PrivacyGate·CloudSafe projection(#135), 캐시·검증(#137), escalation(#140).
- 라우터를 살아있는 호출 경로에 연결(gateway가 소비할 #136).
- 기존 `LLMClient`/`OpenAIClient`/`MockLLMClient`/`LocalLLMProvider` 동작 변경.
- DB 모델·마이그레이션, HTTP 라우터·schema 변경.

## 3. 계약

### 3.1 `LLM_PROVIDER` 설정 (`app/core/config.py`)

기존 `MARKET_PROVIDER` 등과 같은 `Literal` 패턴을 따른다.

| 필드 | 타입 | 기본값 | 책임 |
|------|------|--------|------|
| `LLM_PROVIDER` | `Literal["cloud", "local", "mock"]` | `"cloud"` | factory가 만들 transport 백엔드 선택 |

- 기본값 `cloud`는 ADR-008 §3.2의 "출시는 클라우드 우선"을 코드 기본 자세로 반영한다.
- 로컬 dev는 `.env`에서 `LLM_PROVIDER=mock`을 택한다(`.env.example`에 명시). 기존
  `OPENAI_API_KEY` 빈값 = mock 흐름 관행과 동일한 opt-in 구조다.

### 3.2 `LLMRouter` (`app/adapters/llm/router.py`)

ADR-008의 `task_type → provider` 매핑을 **데이터**로 표현한다. `if task_type == ...`
체인을 두지 않는다.

#### `TaskRoute` (보조 값 객체)

작업별 launch provider와 미래 귀착지를 함께 기록한다(ADR-008 §3.3 — target을 구전이
아닌 문서로).

| 필드 | 타입 | 책임 |
|------|------|------|
| `launch` | `str` | 출시 시 resolve가 돌려주는 provider |
| `future_primary` | `str` | 로컬 성숙 시 이관 1순위 귀착지(기록용) |

- `@dataclass(frozen=True)` 불변 값 객체.

#### 라우팅 표

ADR-008 §3.3("출시 시 라우팅되는 모든 작업은 클라우드로 귀결")에 따라 **launch는 전
작업 `cloud`**, `future_primary`만 작업별로 ADR-008 §4 표를 따른다. 정본 표는 Epic
#141이며 본 표는 그 사본이다.

| `LLMTaskType` | `launch` | `future_primary` |
|---------------|----------|------------------|
| `NEWS_SUMMARY` | `cloud` | `local` |
| `THESIS_CONFLICT` | `cloud` | `cloud` |
| `PORTFOLIO_BRIEFING` | `cloud` | `cloud` |
| `DASHBOARD_BRIEFING` | `cloud` | `local` |
| `WATCHLIST_NOTE` | `cloud` | `local` |
| `TAG_SENTIMENT` | `cloud` | `local` |
| `AGENT` | `cloud` | `cloud` |

- 정의된 `LLMTaskType` 전 멤버가 표에 있어야 한다. 누락은 fail-closed로 드러난다.

#### 메서드

| 메서드 | 시그니처 | 책임 |
|--------|----------|------|
| `resolve` | `(task_type: LLMTaskType) -> str` | 표에서 `launch` provider 반환. 미정의 task_type은 fail-closed(`LLMRoutingError`) |

- sensitivity/risk/health/fallback 기준은 본 범위에서 구현하지 않는다. 데이터 주도
  표 자체가 확장 자리이며, 위험도 기반 escalation은 #140이다(`resolve`에 죽은 파라미터를
  미리 두지 않는다).

#### 라우팅 예외 (`app/adapters/llm/exceptions.py`)

| 타입 | 기반 | 책임 |
|------|------|------|
| `LLMRoutingError` | 기존 LLM 예외 계열 | 매핑 없는 `task_type` 라우팅 시도(fail-closed) |

### 3.3 factory 배선 (`app/adapters/factory.py`)

기존 `get_*_provider()` 패턴을 따라 transport 선택 함수를 추가한다.

| 함수 | 시그니처 | 책임 |
|------|----------|------|
| `get_llm_client` | `(provider: str \| None = None) -> LLMClient` | `provider`(없으면 `settings.LLM_PROVIDER`) 기준 transport 생성 |

- 분기:
  - `"cloud"` → `OpenAIClient(api_key=...)`. 키 부재 시 명확한 에러(시스템 경계).
  - `"local"` → `LocalLLMProvider()`.
  - `"mock"` → `MockLLMClient(DEFAULT_MOCK_RESPONSES)`(§3.4).
  - 그 외 → `NotImplementedError`/`ValueError`(기존 factory 스타일에 맞춤).
- `get_llm_gateway()`는 본 작업에 두지 않는다(#136). 라우터와 factory는 독립 seam으로
  도입하고, 둘을 묶는 조립은 gateway가 소유한다.

### 3.4 mock 캔드 응답 이전 (`app/adapters/llm/mock.py`)

현재 `app/worker/jobs/analysis.py`가 인라인 `MockLLMClient({...})`로 들고 있는 캔드
응답(`NewsSummaryResult`·`ThesisConflictResult`)을 `mock.py` 모듈 상수
`DEFAULT_MOCK_RESPONSES`로 옮긴다.

- 값·구조는 현행과 동일하게 보존(동작 회귀 없음).
- factory `mock` 분기가 이 상수로 `MockLLMClient`를 시드한다.
- `MockLLMClient` 자체의 시그니처·기본 동작은 불변(`responses` 인자 그대로).

### 3.5 worker job 정리 (`app/worker/jobs/analysis.py`)

- 인라인 `MockLLMClient({...})` 생성과 그 import를 제거한다.
- `WatchlistAnalysisService(db, get_llm_client(), get_news_adapter())`로 client를
  factory 경유로 주입한다. 서비스 시그니처(`llm_client: LLMClient`)는 불변.
- dev에서 `LLM_PROVIDER=mock`이면 §3.4 캔드 응답이 흐르므로 기존 mock 분석 산출이
  보존된다.

## 4. 검증

- `uv run ruff check .`
- `uv run mypy .` — 신규 코드 전 필드·메서드에 타입 주석(과거 #126 `no-untyped-def`
  CI 실패 전례).
- `uv run pytest -q` — 신규 테스트:
  - `LLMRouter.resolve`가 각 `LLMTaskType`에 대해 `launch`(=`cloud`)를 반환.
  - 라우팅 표가 `LLMTaskType` 전 멤버를 덮는다(누락 시 실패).
  - 미정의 task_type resolve가 `LLMRoutingError`(fail-closed).
  - `get_llm_client("mock")`가 `MockLLMClient`, `"local")`가 `LocalLLMProvider`를 반환.
  - `get_llm_client("cloud")`가 키 주입 시 `OpenAIClient`, 키 부재 시 명확한 에러.
  - 미지 provider 문자열은 에러.
  - 기존 worker/analysis 테스트가 계속 통과(회귀 없음).

## 5. 비고

- 이슈 #134 본문은 `get_llm_gateway()`를 언급하나, ADR-008 Follow-up이 gateway.py
  조립을 #136 소유로 명시하므로 본 설계는 `get_llm_client()`만 도입하고 gateway는
  이연한다. 라우터는 도입·테스트하되 소비는 #136이다(#133의 타입 선행 패턴과 동일).
- `LLM_PROVIDER` 기본 `cloud`는 ADR-008 §3.2를 따른다. 코드 기본은 클라우드 우선,
  로컬 dev는 `.env`로 mock을 택하는 구조다. 테스트는 provider를 명시 주입/override해
  default `cloud`(키 부재) 경로에 의존하지 않는다.
- 라우터의 `resolve`는 Phase 1에서 전 작업 `cloud`를 돌려준다. `LLM_PROVIDER` 설정과의
  결합 정책(예: dev에서 mock 전역 override)은 gateway(#136)가 소유하며 본 범위가 아니다.
