from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class QuoteResult:
    symbol: str
    name: str
    price: Decimal
    previous_close: Decimal
    change: Decimal
    change_percent: Decimal
    currency: str
    as_of: datetime


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        """Return current market quotes for the given symbols."""
