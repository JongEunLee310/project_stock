# 076 · LLM Cloud 경로 마감 — 실행 메타 기록·timeout 전달·모델 설정화

Status: Draft
작성: Claude Code (orchestrator)
관련: 구현 이슈 BE #200, Epic BE #141(Phase 1 후속 마감), Milestone LLM 하이브리드
아키텍처 — 백엔드(#4). 기준 문서 `docs/knowledge/llm-data-pipeline.md`(§3.5 추적성,
§6.8 Gateway 책임). 선행 설계 `docs/designs/053-llm-provider-types.md`,
`054-llm-router-factory.md`, `056-llm-gateway.md`, `074-llm-analysis-orchestration.md`,
`075-llm-analysis-route-trigger.md`.

## 1. 배경

Phase 1(#132–136)로 `OpenAIClient`·`LLMRouter`·`PrivacyGate`·`LLMGateway`가 구현되었고
PR #199로 실행 진입점까지 배선되어, `LLM_PROVIDER=cloud` 전환의 구조적 준비는 끝났다.
그러나 cloud 경로를 실사용 상태로 만드는 마감 세 가지가 비어 있다.

- `LLMAnalysisService`가 성공 run에 `model_name=None, provider=None`을 저장한다. 게이트웨이가
  어느 provider·모델로 응답했는지 호출자에게 알려주지 않기 때문이다. 지침 §3.5(어떤 입력·
  모델로 그 결과가 나왔는지 재현 가능해야 한다)가 미완이다.
- `LLM_TIMEOUT_SECONDS`가 `config.py`에 정의만 되어 있고 어떤 호출 경로에도 전달되지 않는다.
  `LLMClient.complete_json(timeout=...)` 인자는 이미 존재하지만 항상 None이다.
- OpenAI 모델명이 `OpenAIClient.__init__` 기본값 `"gpt-4o-mini"`로 고정되어 설정으로 바꿀 수
  없다.

새 계층을 만들지 않는다. 기존 `LLMClient` ABC·factory 주입 선례를 그대로 잇고, 게이트웨이
반환값에 실행 메타를 동봉하는 것이 전부다.

## 2. 범위

포함:

- `app/adapters/llm/base.py`(수정): `LLMClient`에 provider·모델 식별 노출.
- `app/adapters/llm/openai.py`·`mock.py`·`local.py`(수정): 식별 값 구현.
- `app/adapters/llm/gateway.py`(수정): 실행 메타 포함 반환 + timeout 전달.
- `app/core/config.py`·`.env.example`(수정): `OPENAI_MODEL` 설정 추가.
- `app/adapters/factory.py`(수정): `OPENAI_MODEL`·`LLM_TIMEOUT_SECONDS` 주입.
- `app/domains/llm_analysis/service.py`(수정): 성공 run에 `model_name`·`provider` 기록.
- 게이트웨이 호출부 3곳(portfolios·watchlists·dashboard briefing service): 반환 타입 적응.
- 단위 테스트(외부 API 없이, mock client 기준).

비포함(후속·변경 없음):

- retry·rate limit·fallback·output validation — Phase 2(#137·#138·#140).
- LLM Cache(#138)·위험도 Escalation(#139).
- `LocalLLMProvider` 실 구현 — stub 유지, 식별 값만 부여.
- 주기 스케줄 등록.
- `LLMAnalysisRun` 모델·신규 alembic revision — `model_name`·`provider` 컬럼 기존재.
- `theses/conflict_service.py`·`news/service.py`의 `LLMClient` 직접 호출 경로 — 게이트웨이
  경유가 아니므로 이번 범위에서 손대지 않는다.

## 3. 구성 요소

### 3.1 클라이언트 식별 (`app/adapters/llm/base.py` 외, 수정)

| 시그니처 | 책임 |
|---|---|
| `LLMClient.provider_name: str` (property) | 클라이언트 구현체의 provider 식별자 |
| `LLMClient.model_name: str` (property) | 호출에 사용하는 모델 식별자 |

구현 값: `OpenAIClient` → `("openai", self.model)`, `MockLLMClient` → `("mock", "mock")`,
`LocalLLMProvider` → `("local", "local-stub")`.

### 3.2 게이트웨이 반환 확장 (`app/adapters/llm/gateway.py`, 수정)

| 시그니처 | 책임 |
|---|---|
| `LLMCompletionResult` (frozen model) | `output: dict` + `provider: str` + `model_name: str` |
| `LLMGateway.__init__(clients, router=None, privacy_gate=None, timeout_seconds=None)` | timeout 주입 지점 |
| `LLMGateway.complete_json(...) -> LLMCompletionResult` | 기존 로직 유지 + 메타 동봉 + `client.complete_json(messages, schema, timeout=...)` 전달 |

`provider`는 클라이언트의 `provider_name`을 기록한다(라우팅 키 `cloud`/`local`이 아니라
실제 구현체 식별자 — mock 조립 시 라우팅 키와 무관하게 `mock`으로 남는다).

### 3.3 설정·factory (`app/core/config.py`·`app/adapters/factory.py`, 수정)

| 항목 | 내용 |
|---|---|
| `OPENAI_MODEL: str = "gpt-4o-mini"` | 신규 설정, `.env.example` 동기화 |
| `get_llm_client("cloud")` | `OpenAIClient(api_key=..., model=settings.OPENAI_MODEL)` |
| `get_llm_gateway()` | `LLMGateway(clients, timeout_seconds=settings.LLM_TIMEOUT_SECONDS)` |

### 3.4 호출부 적응

| 파일 | 변경 |
|---|---|
| `app/domains/llm_analysis/service.py` | `result.output` 사용, `mark_succeeded(model_name=result.model_name, provider=result.provider)` |
| `app/domains/portfolios/briefing_service.py` | 반환값 `.output` 접근으로 적응 |
| `app/domains/watchlists/observations_service.py` | 동일 |
| `app/domains/dashboard/briefing_service.py` | 동일 |

## 4. Decisions

- **Decision UU — 게이트웨이 반환 타입을 `LLMCompletionResult`로 변경한다.** 별도 메서드
  (`complete_json_with_meta`) 추가는 호출부마다 다른 계약이 퍼지므로 기각. 호출부가 4곳뿐인
  지금이 반환 타입을 한 번에 바꿀 가장 싼 시점이다.
- **Decision VV — 실행 메타는 클라이언트 자신이 노출한다(`provider_name`·`model_name`).**
  게이트웨이의 라우팅 키(`cloud`/`local`)는 조립 형상에 따라 실제 구현체와 어긋날 수 있다
  (mock 조립은 두 키 모두 mock). run에 남길 값은 "무엇이 응답했는가"이므로 구현체 식별자를
  기록한다.
- **Decision WW — timeout은 factory에서 게이트웨이 생성자로 주입한다.** 게이트웨이가
  `settings`를 직접 읽으면 어댑터 계층에 설정 의존이 스며든다. 기존 factory 주입 선례
  (`OPENAI_API_KEY`)를 잇는다.
- **Decision XX — `OPENAI_MODEL`은 단일 전역 설정으로 시작한다.** task_type별 모델 매핑은
  Phase 2 라우팅 고도화(#140 접점)에서 필요해질 때 `TaskRoute` 확장으로 다룬다. 지금 도입하면
  근거 없는 추측 설계다.

## 5. 마이그레이션

없음. `llm_analysis_runs.model_name`·`provider` 컬럼은 7단계에서 이미 생성됐다. 단일 head 유지.

## 6. 테스트

- 게이트웨이가 mock client로 `LLMCompletionResult(output, provider="mock", model_name="mock")`을
  반환한다.
- 게이트웨이에 주입한 `timeout_seconds`가 `client.complete_json`의 `timeout` 인자로 전달된다
  (스파이 client).
- `LLM_PROVIDER=mock` 기준 `run_analysis` 성공 run에 `provider`·`model_name`·`prompt_version`이
  저장된다.
- factory가 `OPENAI_MODEL` 설정을 `OpenAIClient.model`에 반영한다(키 존재 시 경로, monkeypatch).
- 기존 briefing·observations·분석 테스트가 반환 타입 적응 후에도 통과한다.

## 7. ADR 판단

불필요. Provider Abstraction·Cloud Data Boundary는 ADR(#132 산출)로 이미 결정되었고, 이
작업은 그 결정의 미완 지점을 채우는 마감이다. 새 아키텍처 선택이 없다.
