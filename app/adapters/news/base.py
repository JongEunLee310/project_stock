from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class NewsAdapterResult:
    title: str
    url: str
    body: str | None
    source: str
    published_at: datetime | None
    payload: dict[str, Any] | None


class NewsAdapter(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str]) -> list[NewsAdapterResult]:
        """Fetch news items matching the given symbols."""
