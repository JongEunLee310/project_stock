# 013: LLM Adapter 기본 구조

## 목적

AI 모델 제공자를 추상화하여 Service가 특정 LLM 구현에 직접 의존하지 않도록 한다.
OpenAI와 Mock을 같은 인터페이스로 사용할 수 있게 한다.

## 모듈 구조

```
app/adapters/llm/
  __init__.py
  base.py           — LLMMessage, LLMClient ABC
  mock.py           — MockLLMClient
  openai.py         — OpenAIClient
  exceptions.py     — LLMCallError, LLMTimeoutError
  prompts/
    __init__.py
```

## 인터페이스

```
@dataclass(frozen=True)
class LLMMessage:
    role: str          # "system" | "user" | "assistant"
    content: str

class LLMClient(ABC):
    def complete(self, messages: list[LLMMessage], timeout: float | None = None) -> str
    def complete_json(self, messages: list[LLMMessage], schema: type[BaseModel], timeout: float | None = None) -> dict[str, Any]
```

- `complete`: 자유 문자열 응답 반환
- `complete_json`: `schema`를 JSON Schema로 변환하여 LLM에 전달, dict 반환
- 타임아웃 초과 시 `LLMTimeoutError` 발생
- 기타 호출 실패 시 `LLMCallError` 발생

## 예외 계층

```
LLMCallError(Exception)
  └─ LLMTimeoutError(LLMCallError)
```

## 설정 추가 (app/core/config.py)

```
OPENAI_API_KEY: str | None = None
LLM_TIMEOUT_SECONDS: int = 30
```

## MockLLMClient

```
class MockLLMClient(LLMClient):
    def __init__(self, responses: dict[str, Any] | None = None)
    def complete(...) -> str
    def complete_json(...) -> dict[str, Any]
```

생성자에 `responses`를 주입하여 테스트별 응답을 제어한다.

## OpenAIClient

```
class OpenAIClient(LLMClient):
    def __init__(self, api_key: str, model: str = "gpt-4o-mini")
    def complete(...) -> str
    def complete_json(...) -> dict[str, Any]
```

`openai.OpenAI` 클라이언트를 사용하며 `response_format={"type": "json_object"}`로 JSON 응답을 강제한다.

## 의존성 추가

`pyproject.toml`에 `openai>=1.0.0` 추가
