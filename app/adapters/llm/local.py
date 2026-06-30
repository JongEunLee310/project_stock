from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage


class LocalLLMProvider(LLMClient):
    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        raise NotImplementedError("Local LLM provider is not ready yet.")

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError("Local LLM provider is not ready yet.")
