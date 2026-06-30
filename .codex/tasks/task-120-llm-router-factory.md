# Codex Handoff Task

## Source Issue

이슈 #134 — [LLM] LLMRouter + factory(get_llm_client)·LLM_PROVIDER 설정, worker 하드코딩 Mock 정리
설계: `docs/designs/054-llm-router-factory.md` (Frozen)
근거 ADR: `ADR-007`(Provider Abstraction)·`ADR-008`(Task Routing)

## Task Summary

provider 선택을 task 인지형으로 확장합니다. `LLMRouter`(task_type→provider 데이터 주도
매핑), `LLM_PROVIDER` 설정, factory `get_llm_client()` 배선을 추가하고,
`app/worker/jobs/analysis.py`의 인라인 `MockLLMClient(...)` 생성을 factory 경유로
정리합니다. **gateway 조립(`get_llm_gateway()`/gateway.py)은 본 범위가 아닙니다**(#136).

## Goal

- `app/adapters/llm/router.py`가 설계 054 §3.2의 `LLMRouter`·라우팅 표·`TaskRoute`를
  정의하고, fail-closed(미정의 task_type → `LLMRoutingError`)로 동작한다.
- `app/core/config.py`에 `LLM_PROVIDER: Literal["cloud","local","mock"] = "cloud"` 추가.
- `app/adapters/factory.py`에 `get_llm_client()` 추가(`settings.LLM_PROVIDER` 기준).
- worker job이 factory 경유로 client를 주입하고 dev mock 동작이 보존된다.
- 기존 동작 불변, 검증 3종 통과.

## Background — 오케스트레이터가 확정한 사실

- 설계 054가 정본이며 계약은 동결됨. 아래대로 구현할 것.
- 전 계층 sync 컨벤션 유지(ADR-007). `async def` 도입 금지.
- enum·봉투·`LocalLLMProvider`는 #133이 이미 도입함(`app/adapters/llm/types.py`·
  `local.py`). 본 작업은 이를 **소비**할 뿐 변경하지 않는다.
- 라우팅 표는 데이터로 둔다(`if task_type == ...` 체인 금지, ADR-008 §3.2).
- ADR-008 §3.3에 따라 **launch는 전 작업 `cloud`**, `future_primary`만 작업별로
  설계 054 §3.2 표를 따른다.
- `get_llm_gateway()`·gateway.py·PrivacyGate·CloudSafe·캐시·검증·escalation은
  구현하지 않는다(#135/#136/#137/#140). 라우터를 살아있는 호출 경로에 연결하지 않는다
  (gateway가 소비할 #136).
- `resolve`에 sensitivity/risk/health/fallback 죽은 파라미터를 미리 두지 않는다. 표가
  곧 확장 자리다.

## Implementation Scope

- `app/core/config.py`
  - `LLM_PROVIDER: Literal["cloud", "local", "mock"] = "cloud"` 추가(기존 `*_PROVIDER`
    필드 바로 아래, 같은 스타일).
- `app/adapters/llm/exceptions.py`
  - `LLMRoutingError` 추가(기존 `LLMCallError`/`LLMTimeoutError`와 같은 계열·기반).
- `app/adapters/llm/router.py` (신규)
  - `TaskRoute` `@dataclass(frozen=True)`: `launch: str`, `future_primary: str`.
  - 모듈 수준 라우팅 표 `dict[LLMTaskType, TaskRoute]`. 설계 054 §3.2 표대로 7개
    `LLMTaskType` 전 멤버를 덮는다(launch 전부 `"cloud"`; future_primary는
    `NEWS_SUMMARY`/`DASHBOARD_BRIEFING`/`WATCHLIST_NOTE`/`TAG_SENTIMENT`=`"local"`,
    `THESIS_CONFLICT`/`PORTFOLIO_BRIEFING`/`AGENT`=`"cloud"`).
  - `class LLMRouter`: `resolve(task_type: LLMTaskType) -> str` — 표에서 `launch`
    반환, 미정의 시 `LLMRoutingError`. (생성자는 인자 없이 모듈 표를 쓰거나, 표를
    선택적 주입받는 단순 형태 중 repo에 자연스러운 쪽. 과한 추상화 금지.)
- `app/adapters/llm/mock.py`
  - 모듈 상수 `DEFAULT_MOCK_RESPONSES: dict[str, Any]` 추가 — 현재
    `app/worker/jobs/analysis.py`가 인라인으로 넘기는 캔드 응답(`NewsSummaryResult`·
    `ThesisConflictResult` dict)을 **값·구조 그대로** 옮긴다.
  - `MockLLMClient`의 시그니처·기본 동작은 변경하지 않는다.
- `app/adapters/factory.py`
  - `get_llm_client(provider: str | None = None) -> LLMClient` 추가:
    - `provider`가 `None`이면 `settings.LLM_PROVIDER` 사용.
    - `"cloud"` → `OpenAIClient(api_key=settings.OPENAI_API_KEY, ...)`. 키가 `None`/빈값이면
      명확한 에러(예 `RuntimeError`/`ValueError`)로 실패.
    - `"local"` → `LocalLLMProvider()`.
    - `"mock"` → `MockLLMClient(DEFAULT_MOCK_RESPONSES)`.
    - 그 외 → 기존 factory 스타일의 에러(`NotImplementedError`/`ValueError`).
  - 기존 import 스타일을 따라 필요한 심볼을 import.
- `app/worker/jobs/analysis.py`
  - 인라인 `MockLLMClient({...})` 생성과 `from app.adapters.llm.mock import MockLLMClient`
    제거.
  - `from app.adapters.factory import get_llm_client` 추가.
  - `WatchlistAnalysisService(db, get_llm_client(), get_news_adapter())`로 변경.
- `app/adapters/llm/__init__.py`
  - 기존 export 스타일을 따라 신규 공개 심볼(`LLMRouter`, `TaskRoute`,
    `LLMRoutingError`)을 재노출(`__all__` 정렬 유지).
- `.env.example`
  - 기존 provider 스위치 블록에 `LLM_PROVIDER=mock` 추가(로컬 dev 기본 mock). 한 줄
    주석으로 "로컬 dev는 mock, 출시 기본은 cloud" 취지 명시.

## Out of Scope

- `get_llm_gateway()`·`app/adapters/llm/gateway.py`·`LLMGateway` 조립(#136).
- PrivacyGate·CloudSafe projection(#135), 캐시·검증(#137), escalation(#140).
- 라우터를 gateway/서비스 진입점에 연결.
- `LLMClient`/`OpenAIClient`/`MockLLMClient`/`LocalLLMProvider`/`types.py` 동작 변경.
- DB 모델·마이그레이션, HTTP 라우터·schema 변경.
- 라우터 `resolve`에 sensitivity/risk 등 파라미터 추가.

## Protected Files

`docs/decisions/`·`docs/harness/`·`AGENTS.md`·`CLAUDE.md`·`.github/workflows/ci.yml`는
건드리지 않는다. 설계 054와 본 핸드오프는 오케스트레이터가 작성함. `.codex/`도 수정 금지.
(`.env.example`은 보호 대상 아님 — 위 스코프대로 한 줄 추가만.)

## Requirements

- mypy strict 통과: 전 필드·메서드·테스트 함수에 타입 주석(과거 #126 `no-untyped-def`
  CI 실패 전례). 라우팅 표·`DEFAULT_MOCK_RESPONSES`에도 명시적 타입 주석.
- 라우팅 표는 `LLMTaskType` 전 멤버를 덮는다(누락 금지).
- fail-closed: 미정의 task_type은 조용한 기본값이 아니라 `LLMRoutingError`.
- 외부 호출·I/O 추가 없음(cloud 분기는 client 생성만, 실제 호출 없음).
- 에러 처리는 시스템 경계(설정/provider 선택)에서만.

## Test Requirements

`tests/adapters/test_llm_router.py`(또는 repo 테스트 배치 컨벤션 위치) 신규:

- `LLMRouter().resolve(task_type)`가 각 `LLMTaskType`에 대해 `"cloud"` 반환.
- 라우팅 표가 `LLMTaskType` 전 멤버를 덮음(예: 전 멤버 순회 resolve가 예외 없이 통과).
- 표에 없는 값/미정의 입력 resolve가 `LLMRoutingError`(fail-closed).
- (선택) 각 작업의 `future_primary`가 설계 054 §3.2 표와 일치.

`tests/adapters/test_llm_factory.py`(또는 동일 컨벤션) 신규:

- `get_llm_client("mock")` → `MockLLMClient` 인스턴스(그리고 `DEFAULT_MOCK_RESPONSES`로
  시드되어 `NewsSummaryResult`/`ThesisConflictResult` 캔드 응답을 돌려줌).
- `get_llm_client("local")` → `LocalLLMProvider` 인스턴스.
- `get_llm_client("cloud")` → `OpenAIClient` 인스턴스(테스트에서 `OPENAI_API_KEY`를
  monkeypatch로 주입). 키 부재 시 명확한 에러.
- 미지 provider 문자열 → 에러.
- `provider=None`일 때 `settings.LLM_PROVIDER`를 따름(monkeypatch로 검증).

기존 `tests/test_worker_jobs.py`·`tests/test_analysis_flow.py` 등은 회귀 없이 계속
통과해야 한다. worker 테스트가 default `cloud`(키 부재) 경로를 타지 않도록, 필요한 경우
`settings.LLM_PROVIDER`를 `mock`으로 monkeypatch하거나 factory를 monkeypatch한다
(테스트가 실제 OpenAI 키에 의존하지 않게 한다).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

- `docs/designs/054-llm-router-factory.md` 추가됨(정본, 오케스트레이터 작성).
- 본 핸드오프 문서 추가.
- README·ADR 변경 불요(ADR-007~008이 이미 결정을 고정).

## ADR Need

불요. ADR-007~008이 본 작업의 결정을 이미 고정했으며, 본 작업은 그 정책을 코드로 배선할
뿐 신규 아키텍처 결정이 없다. (`LLM_PROVIDER` 기본 `cloud`·gateway 이연은 ADR-008 본문·
Follow-up을 그대로 따른 것이며 설계 054 §5에 근거를 기록함.)

## Failure Record Need

불요. 국소 추가·리팩터링, 회귀는 기존+신규 테스트로 커버.

## Risk Level

Low. config 주도 라우터·factory 배선과 worker import 정리. 기존 동작 보존(캔드 응답
이전으로 dev mock 산출 불변), 외부 호출 없음.

## Expected Output

- `app/adapters/llm/router.py`(신규)·`get_llm_client()`(factory)·`LLM_PROVIDER`(config)·
  `LLMRoutingError`(exceptions)·`DEFAULT_MOCK_RESPONSES`(mock)·analysis.py 정리·
  `__init__.py` 재노출·`.env.example` 한 줄.
- 위 신규 테스트 2종 + 기존 테스트 회귀 없음.
- 최신 `main`에서 분기한 feature 브랜치(`feat/llm-router-factory`)에 커밋(한국어 메시지,
  `type: 본문` 형식).
- 검증 3종 통과 결과 보고.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
