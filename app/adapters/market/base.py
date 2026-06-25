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


@dataclass(frozen=True)
class PriceBarResult:
    symbol: str
    market: str
    interval: str
    timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    adjusted_close_price: Decimal
    volume: int
    currency: str
    source: str


class PriceSeriesProvider(ABC):
    @abstractmethod
    def get_daily_bars(
        self,
        symbol: str,
        market: str,
        range_value: str,
        adjusted: bool,
    ) -> list[PriceBarResult]:
        """Return deterministic daily OHLCV bars for the given symbol and market."""
