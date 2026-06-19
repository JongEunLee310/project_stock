from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage


class MockLLMClient(LLMClient):
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}

    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        return "mock response"

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        response = self.responses.get(schema.__name__, self.responses.get("default", {}))
        if isinstance(response, dict):
            return response
        return {"response": response}
