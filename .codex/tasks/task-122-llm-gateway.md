# Codex Handoff Task

## Source Issue

JongEunLee310/project_stock#136 — [LLM] LLMGateway 오케스트레이터 조립 + Phase 1 테스트

설계: `docs/designs/056-llm-gateway.md` (Status: Frozen) — 본 핸드오프는 이 설계를 그대로
구현한다.

## Task Summary

`LLMRouter`(#134)와 `PrivacyGate`(#135)를 단일 진입점 `LLMGateway`로 묶는다. 게이트웨이는
task_type으로 provider를 고르고, 클라우드 경로에서 페이로드를 프라이버시 검사한 뒤
선택된 transport에 위임한다. 조립과 Phase 1 경계 테스트까지이며, 살아있는 소비처 이관은
범위가 아니다.

## Goal

작업 완료 시 다음이 참이어야 한다:

- `app/adapters/llm/gateway.py`에 `LLMGateway`가 존재하고, 라우터·프라이버시 게이트·
  transport 맵을 조립한다.
- `complete_json`이 클라우드 경로에서 비-CloudSafe 페이로드(원본 entity)와 `RAW`/`SEMI`
  CloudSafe 페이로드를 `CloudBoundaryViolationError`로 차단하고, 검사를 통과한 CloudSafe
  projection의 `as_payload()` 본문만 transport에 전달한다.
- task_type에 따라 provider가 선택되고, 기본 라우팅 표에서는 `LocalLLMProvider`가 실제로
  호출되지 않는다.
- `app/adapters/factory.py`에 `get_llm_gateway()`가 추가된다(조립 seam, 소비처 없음).
- `ruff`/`mypy`/`pytest`가 모두 통과한다.

## Background

- ADR-007이 모든 클라우드 호출 앞 단일 choke point를, ADR-009 §4가 transport 선택 전
  게이트웨이 내부 경계 검사를 못박았다. ADR-008 §3.2에 따라 출시는 클라우드 우선이라
  모든 task가 `cloud`로 라우팅된다.
- `LLMRouter`(`resolve(task_type) -> str`), `PrivacyGate`(`guard(payload) -> CloudSafePayload`),
  `CloudSafePayload`/`PortfolioConcentrationSnapshot`/`to_concentration_snapshot`,
  `CloudBoundaryViolationError`, `LLMRoutingError`, `LLMRequest`/`LLMResponse`,
  `LLMClient`/`LLMMessage`, `MockLLMClient`, `LocalLLMProvider`, `OpenAIClient`는 이미
  `app/adapters/llm/`에 있다. 재정의하지 말고 import해 쓴다.
- 본 작업은 #133 타입·#134 라우터·#135 프라이버시와 같은 "도입 후 소비는 후속" 패턴이다.
  살아있는 호출 경로는 건드리지 않는다.

## Implementation Scope

Codex가 변경해도 되는 파일:

- `app/adapters/llm/gateway.py` (신규) — 설계 §3.1:
  - `LLMGateway(clients: Mapping[str, LLMClient], router: LLMRouter | None = None,
    privacy_gate: PrivacyGate | None = None)`. `router`/`privacy_gate`가 `None`이면 각각
    기본 `LLMRouter()`/`PrivacyGate()`로 채운다.
  - `complete_json(task_type: LLMTaskType, payload: CloudSafePayload,
    schema: type[BaseModel], system_prompt: str) -> dict[str, Any]`:
    1. `provider = router.resolve(task_type)`.
    2. `clients`에서 provider transport 조회. 없으면 `LLMRoutingError`(fail-closed).
    3. provider가 `"cloud"`면 `privacy_gate.guard(payload)`로 검사한 결과만 본문으로
       사용. `"local"`이면 검사 면제(Phase 1에서는 도달하지 않음).
    4. 검사 통과 페이로드의 `as_payload()`(dict)와 `system_prompt`로
       `list[LLMMessage]` 구성(system + user). 원본 entity는 본문에 넣지 않는다.
    5. `client.complete_json(messages, schema)`에 위임해 결과 dict 반환.
  - provider 이름 비교는 모듈 상수(예: `CLOUD = "cloud"`, `LOCAL = "local"`)로.
- `app/adapters/factory.py` — `get_llm_gateway() -> LLMGateway` 추가(설계 §3.2):
  - `settings.LLM_PROVIDER` 기준 transport 맵 구성. `mock`이면 단일 `MockLLMClient`를
    두 슬롯에, `cloud`/`local`이면 설계 §3.2 표대로 매핑. 기존 `get_llm_client()` 재사용.
- `app/adapters/llm/__init__.py` — `LLMGateway` re-export. `__all__` 알파벳 정렬 유지.
- `tests/` — 신규 `tests/test_llm_gateway.py`.

## Out of Scope

- `NewsAnalysisService`·`ThesisAnalysisService` 등 살아있는 소비처를 게이트웨이로 이관
  (시그니처·동작 불변 = 호환 유지).
- 텍스트 `complete`(자유형) 진입점.
- 캐시·검증(#137), escalation(#140), 추가 CloudSafe projection·재식별 정밀화(Phase 2).
- `LLMResponse` 봉투 조립(latency·token·model).
- 라우터/privacy/transport 자체 동작 변경. DB 모델·마이그레이션, HTTP·worker 변경.

## Protected Files

없음. 보호 파일(`docs/decisions/`, `docs/harness/`, `AGENTS.md`, `CLAUDE.md`, `.codex/`,
`.github/workflows/ci.yml`)은 변경하지 않는다. 설계 `docs/designs/056-*.md`는 이미
작성되어 있으니 수정하지 않는다.

## Requirements

- 경계 검사는 transport 선택·호출 전에, 게이트웨이 내부에서만(우회 불가).
- 클라우드 경로는 fail-closed: 비-CloudSafe·`RAW`/`SEMI`는 차단하고 transport를 호출하지
  않는다.
- transport에 전달되는 본문은 `as_payload()`를 거친 CloudSafe projection 뿐. 원본 entity
  직렬화 금지.
- 기존 코드 동작 변경 없음. 라이브 호출 경로를 건드리지 않는다.
- 에러 처리는 경계에서만. 불필요한 추상화(텍스트 경로·응답 봉투 등) 추가 금지.

## Test Requirements

`tests/test_llm_gateway.py`(신규):

- 원본 `Portfolio` entity를 payload로 넘기면 `CloudBoundaryViolationError`로 차단되고,
  주입한 클라우드 transport의 `complete_json`이 호출되지 않는다(스파이/카운터로 확인).
- `RAW`/`SEMI`를 선언한 CloudSafe 테스트용 서브클래스 payload도 차단된다.
- `PortfolioConcentrationSnapshot`(AGGREGATED)은 통과하고, transport에 전달된 메시지
  본문이 `as_payload()` 결과(구간·불리언)만 담으며 `user_id`·절대 수량·잔액·종목
  식별자를 담지 않는다.
- task_type에 따라 provider가 선택된다(라우터 경유).
- 기본 라우팅 표에서 어떤 task도 `local`로 가지 않아 `LocalLLMProvider`가 실제로
  호출되지 않는다(`NotImplementedError`가 발생하지 않음).
- `MockLLMClient`를 `"cloud"` 슬롯에 주입해 게이트웨이/라우터 전체 경로가 동작한다.
- 기존 LLM/worker/analysis 테스트가 계속 통과(회귀 없음).

## Verification Commands

- `uv run ruff check .`
- `uv run mypy .`
- `uv run pytest -q`

## Documentation Impact

설계 `docs/designs/056-llm-gateway.md`가 이미 본 작업을 기술한다. 추가 문서 변경은
불필요하다. ADR-007·008·009가 근거이며 본 구현이 그 조립 단계다.

## ADR Need

불필요. ADR-007(choke point)·008(routing)·009(boundary)가 이미 결정을 확정했고 본 작업은
그 조립이다.

## Failure Record Need

불필요. 신규 기능 도입이며 회귀·장애 대응이 아니다.

## Risk Level

Medium. 프라이버시·보안 경계 코드이나, 도입 후 소비는 후속이라 라이브 경로 동작 변경이
없다. 단, ADR-009 Consequences에 따라 **머지 전 명시적 사람 리뷰가 필수**다(로컬 리뷰 후
개발자 최종 승인).

## Expected Output

- 위 Implementation Scope의 파일 변경.
- feature 브랜치 `feat/llm-gateway`에 커밋, PR 생성(`Closes #136`).
- 세 검증 커맨드 통과 로그.

## Rules

- Stay within scope.
- Do not weaken verification.
- Do not modify protected files unless listed above.
- Report assumptions and verification results.
