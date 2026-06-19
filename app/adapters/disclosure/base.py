from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class DisclosureResult:
    symbol: str
    title: str
    url: str
    source: str
    published_at: datetime
    payload: dict[str, Any] | None


class DisclosureProvider(ABC):
    @abstractmethod
    def fetch(self, symbols: list[str]) -> list[DisclosureResult]:
        """Fetch disclosures matching the given symbols."""
