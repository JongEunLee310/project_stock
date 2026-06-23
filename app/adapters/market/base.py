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
    per: Decimal | None = None
    peg: Decimal | None = None
    fifty_two_week_low: Decimal | None = None
    fifty_two_week_high: Decimal | None = None
    target_price: Decimal | None = None
    target_upside_percent: Decimal | None = None


class MarketDataProvider(ABC):
    @abstractmethod
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        """Return current market quotes for the given symbols."""
