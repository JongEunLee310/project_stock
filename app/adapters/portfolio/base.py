from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class HoldingResult:
    account_ref: str
    symbol: str
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    currency: str
    payload: dict[str, Any] | None


class PortfolioProvider(ABC):
    @abstractmethod
    def fetch_holdings(self, account_ref: str) -> list[HoldingResult]:
        """Fetch portfolio holdings for the given account reference."""
