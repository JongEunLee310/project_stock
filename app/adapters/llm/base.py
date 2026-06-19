from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel


@dataclass(frozen=True)
class LLMMessage:
    role: str
    content: str


class LLMClient(ABC):
    @abstractmethod
    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        """Return a free-form text completion."""

    @abstractmethod
    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Return a JSON object completion matching the given schema."""
