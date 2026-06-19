# Codex Handoff Task

## Source Issue

Issue #13: LLM Adapter 기본 구조 구현

## Task Summary

AI 모델 제공자 추상화 레이어를 구현한다. `LLMClient` ABC, `MockLLMClient`, `OpenAIClient`를 작성하고 타임아웃·예외 처리를 포함한다.

## Goal

- Service가 특정 LLM 제공자에 직접 의존하지 않는다.
- `MockLLMClient`로 LLM 호출 없이 테스트가 가능하다.
- LLM 호출 실패 시 `LLMCallError`, 타임아웃 시 `LLMTimeoutError`가 발생하고 시스템이 중단되지 않는다.

## Background

- **설계 문서를 구현 전에 반드시 읽는다:** `docs/designs/013-llm-adapter.md`
- 뉴스 Adapter 패턴(`app/adapters/news/base.py`)을 참고하여 동일한 구조로 작성한다.
- `openai` 패키지가 아직 없으므로 `pyproject.toml`에 추가해야 한다.
- `LLMClient.complete_json`은 Pydantic 모델의 `model_json_schema()`를 OpenAI `response_format` 또는 system prompt에 포함하여 JSON 응답을 강제한다.
- `complete_json` 반환 타입은 `dict[str, Any]`이며, 호출 측이 Pydantic으로 파싱한다.

## Implementation Scope

- `pyproject.toml` — `openai>=1.0.0` 추가
- `uv.lock` — `uv lock` 재실행
- `app/adapters/llm/__init__.py`
- `app/adapters/llm/base.py` — `LLMMessage`, `LLMClient` ABC
- `app/adapters/llm/mock.py` — `MockLLMClient`
- `app/adapters/llm/openai.py` — `OpenAIClient`
- `app/adapters/llm/exceptions.py` — `LLMCallError`, `LLMTimeoutError`
- `app/adapters/llm/prompts/__init__.py`
- `app/core/config.py` — `OPENAI_API_KEY: str | None = None`, `LLM_TIMEOUT_SECONDS: int = 30` 추가
- `tests/test_llm_adapter.py`

## Out of Scope

- Anthropic SDK 통합
- 스트리밍 응답
- 토큰 계산 / 비용 추적
- 프롬프트 파일 작성 (Issue #14, #15에서 수행)

## Protected Files

변경하지 않는 파일:
- `AGENTS.md`, `CLAUDE.md`
- `.github/workflows/ci.yml`
- `docs/harness/`, `docs/decisions/`

## Requirements

### app/adapters/llm/base.py

```python
@dataclass(frozen=True)
class LLMMessage:
    role: str       # "system" | "user" | "assistant"
    content: str

class LLMClient(ABC):
    @abstractmethod
    def complete(self, messages: list[LLMMessage], timeout: float | None = None) -> str: ...

    @abstractmethod
    def complete_json(self, messages: list[LLMMessage], schema: type[BaseModel], timeout: float | None = None) -> dict[str, Any]: ...
```

### app/adapters/llm/exceptions.py

```python
class LLMCallError(Exception): ...
class LLMTimeoutError(LLMCallError): ...
```

### MockLLMClient

- 생성자에 `responses: dict[str, Any] | None = None` 주입
- `complete`: 고정 문자열 반환 (기본값: `"mock response"`)
- `complete_json`: `responses`에서 조회하거나 빈 dict 반환 (`schema`를 무시해도 됨)
- 외부 I/O 없음 — 테스트에서 네트워크 연결 불필요

### OpenAIClient

- `__init__(self, api_key: str, model: str = "gpt-4o-mini")`
- `complete`: `openai.OpenAI(api_key=api_key).chat.completions.create(...)` 호출
- `complete_json`: system prompt에 JSON Schema 삽입 후 `response_format={"type": "json_object"}` 사용
- `timeout` 파라미터를 OpenAI SDK의 `timeout`으로 전달
- `openai.APITimeoutError` → `LLMTimeoutError` 변환
- 그 외 `openai.OpenAIError` → `LLMCallError` 변환

### app/core/config.py 변경

`Settings`에 아래 두 필드 추가:
```python
OPENAI_API_KEY: str | None = None
LLM_TIMEOUT_SECONDS: int = 30
```

## Test Requirements

`tests/test_llm_adapter.py`:

- `MockLLMClient.complete` — 기본 응답 반환 검증
- `MockLLMClient.complete_json` — 주입된 responses 반환 검증
- `OpenAIClient.complete` — `openai.OpenAI` 를 mock 처리, 정상 응답 검증
- `OpenAIClient.complete` — `openai.APITimeoutError` 발생 시 `LLMTimeoutError` 변환 검증
- `OpenAIClient.complete` — `openai.OpenAIError` 발생 시 `LLMCallError` 변환 검증
- `OpenAIClient.complete_json` — JSON 응답 파싱 검증

## Verification Commands

```bash
uv run ruff check .
uv run mypy .
uv run pytest tests/test_llm_adapter.py -v
```

## Documentation Impact

없음.

## ADR Need

없음 — OpenAI 선택은 MVP 단계의 가역적 결정, 인터페이스 추상화로 교체 가능.

## Failure Record Need

없음.

## Risk Level

Low — 신규 모듈 추가. 기존 코드 변경은 `app/core/config.py`의 필드 추가만.

## Expected Output

- 위 scope 파일 전체 신규 생성
- `pyproject.toml`에 `openai>=1.0.0` 추가
- `uv run pytest tests/test_llm_adapter.py` 통과
- lint/typecheck 통과

## Rules

- 구현 전 `docs/designs/013-llm-adapter.md`를 읽고 인터페이스·모듈 구조를 설계 문서 기준으로 구현한다.
- `app/adapters/news/base.py` 패턴을 참고한다.
- OpenAI SDK는 `unittest.mock.patch`로 테스트한다 — 실제 API 호출 금지.
- 스코프 외 파일 변경 금지.
- 테스트 약화 금지.
- 보호 파일 변경 금지.
