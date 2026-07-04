# Codex Handoff Task

## Source Issue

- BE #200 — [LLM] Cloud 경로 마감 — 실행 메타 기록·timeout 전달·모델 설정화
- Epic BE #141 (Phase 1 후속 마감)
- 설계: `docs/designs/076-llm-cloud-path-completion.md`

## Task Summary

`LLMGateway.complete_json`이 실행 메타(provider·model_name)를 담은 `LLMCompletionResult`를
반환하도록 확장하고, `LLM_TIMEOUT_SECONDS`를 실제 client 호출 timeout으로 전달하며,
OpenAI 모델명을 `OPENAI_MODEL` 설정으로 뺀다. `LLMAnalysisService`는 성공 run에
`model_name`·`provider`를 기록한다.

## Goal

- `LLM_PROVIDER=cloud`에서 성공한 `LLMAnalysisRun`에 provider·model_name이 저장된다.
- `LLM_TIMEOUT_SECONDS`가 `LLMClient.complete_json(timeout=...)`으로 전달된다.
- `OPENAI_MODEL` 설정으로 호출 모델을 변경할 수 있다.
- mock 경로 기존 테스트가 깨지지 않는다.

## Background

- `app/adapters/llm/gateway.py`의 `complete_json`은 현재 `dict[str, Any]`만 반환하고
  timeout을 전달하지 않는다.
- `app/domains/llm_analysis/service.py`는 `mark_succeeded(model_name=None, provider=None)`로
  저장한다. `llm_analysis_runs.model_name`·`provider` 컬럼은 이미 존재한다(마이그레이션 불필요).
- `LLMClient.complete_json`의 `timeout: float | None` 인자는 base ABC에 이미 존재한다.
- 게이트웨이 호출부는 4곳: `llm_analysis/service.py`, `portfolios/briefing_service.py`,
  `watchlists/observations_service.py`, `dashboard/briefing_service.py`.
- `theses/conflict_service.py`·`news/service.py`는 `LLMClient`를 직접 쓰는 경로이므로 변경 금지.

## Implementation Scope

1. `app/adapters/llm/base.py` — `LLMClient`에 `provider_name: str`·`model_name: str`
   property(또는 추상 property) 추가.
2. 구현체 식별 값:
   - `OpenAIClient` → `provider_name="openai"`, `model_name=self.model`
   - `MockLLMClient` → `("mock", "mock")`
   - `LocalLLMProvider` → `("local", "local-stub")`
3. `app/adapters/llm/gateway.py`:
   - `LLMCompletionResult`(frozen pydantic model 또는 frozen dataclass):
     `output: dict[str, Any]`, `provider: str`, `model_name: str`
   - `LLMGateway.__init__`에 `timeout_seconds: float | None = None` 추가
   - `complete_json` 반환 타입을 `LLMCompletionResult`로 변경, `client.complete_json(messages,
     schema, timeout=self.timeout_seconds)` 전달, 메타는 선택된 client의 property에서 채움
4. `app/core/config.py` — `OPENAI_MODEL: str = "gpt-4o-mini"` 추가, `.env.example` 동기화.
5. `app/adapters/factory.py`:
   - `get_llm_client("cloud")`가 `OpenAIClient(api_key=..., model=settings.OPENAI_MODEL)` 생성
   - `get_llm_gateway()`가 `timeout_seconds=settings.LLM_TIMEOUT_SECONDS` 주입 (모든 분기)
6. `app/domains/llm_analysis/service.py` — `result = self.gateway.complete_json(...)` 후
   `result.output`으로 검증하고 `mark_succeeded(model_name=result.model_name,
   provider=result.provider, prompt_version=ANALYSIS_PROMPT_VERSION)` 기록.
7. 호출부 적응 — `portfolios/briefing_service.py`·`watchlists/observations_service.py`·
   `dashboard/briefing_service.py`에서 게이트웨이 반환값 `.output` 접근으로 최소 수정.
8. 테스트 추가·갱신 (아래 Test Requirements).

## Out of Scope

- retry·rate limit·fallback·output validation (Phase 2 #137·#138·#140)
- LLM Cache·Escalation
- `LocalLLMProvider` 실 구현 (식별 값 부여 외 stub 유지)
- 주기 스케줄 등록
- `theses/conflict_service.py`·`news/service.py`의 직접 호출 경로
- 신규 alembic revision

## Protected Files

- `app/domains/llm_analysis/model.py` — 변경 금지
- `app/domains/llm_analysis/repository.py` — 변경 금지
- `app/adapters/llm/privacy.py`·`router.py`·`prompts/` — 변경 금지
- `app/worker/jobs/llm_analysis.py` — 변경 금지
- `alembic/` — 신규 revision 금지

## Requirements

- sync 유지 (async 전환 금지)
- 게이트웨이가 `settings`를 직접 읽지 않는다 — factory 주입 (설계 076 Decision WW)
- provider 기록 값은 라우팅 키가 아니라 client 구현체 식별자 (Decision VV)
- 타입 힌트 완전성 (mypy no-untyped-def 통과 수준)
- 주석은 WHY가 필요한 곳에만 최소

## Test Requirements

- 게이트웨이: mock client로 `LLMCompletionResult(output, provider="mock", model_name="mock")`
  반환 검증
- 게이트웨이: `timeout_seconds` 주입 시 `client.complete_json`의 `timeout` 인자로 전달되는지
  스파이 client로 검증
- 서비스: `run_analysis` 성공 run에 `provider`·`model_name`·`prompt_version` 저장 검증
  (`tests/test_llm_analysis_service.py` 갱신)
- factory: `OPENAI_MODEL` 설정이 `OpenAIClient.model`에 반영되는지 검증 (API 키 monkeypatch)
- 기존 briefing·observations·분석·라우트 테스트 전부 통과 (반환 타입 적응 포함)

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest
uv run alembic heads
```

## Documentation Impact

설계 `docs/designs/076-llm-cloud-path-completion.md`가 이 PR에 동봉된다. 지침서·ADR 갱신 불필요.

## ADR Need

없음 — 설계 076 §7 참조.

## Failure Record Need

없음.

## Risk Level

낮음. 반환 타입 변경은 컴파일 타임(mypy)에 호출부 누락이 드러나고, DB 스키마 변경이 없다.

## Expected Output

- 수정: `app/adapters/llm/base.py`, `openai.py`, `mock.py`, `local.py`, `gateway.py`,
  `app/core/config.py`, `.env.example`, `app/adapters/factory.py`,
  `app/domains/llm_analysis/service.py`, briefing 호출부 3곳
- 테스트: 게이트웨이·factory·서비스 테스트 갱신·추가
- 검증 4종 통과

## Decisions 요약 (설계 076 참조)

- UU: 게이트웨이 반환 타입을 `LLMCompletionResult`로 변경 (별도 메서드 추가 기각)
- VV: 실행 메타는 client 구현체가 노출 (`provider_name`·`model_name`)
- WW: timeout은 factory에서 게이트웨이 생성자 주입
- XX: `OPENAI_MODEL` 단일 전역 설정 (task_type별 매핑은 Phase 2)
