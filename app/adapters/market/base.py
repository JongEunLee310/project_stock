from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date, datetime
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
    market_cap: Decimal | None = None
    next_earnings_date: str | None = None
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

    @abstractmethod
    def get_intraday_bars(
        self,
        symbol: str,
        market: str,
    ) -> list[PriceBarResult]:
        """Return 15-minute OHLCV bars for the current trading day."""


@dataclass(frozen=True)
class IndexQuoteResult:
    symbol: str
    name: str
    value: Decimal
    change_percent: Decimal
    reference_at: datetime


class IndexQuoteProvider(ABC):
    @abstractmethod
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
        """Return current market index quotes for the given symbols."""


@dataclass(frozen=True)
class ExchangeRateResult:
    pair: str
    rate: Decimal
    change_percent: Decimal
    as_of: datetime


class ExchangeRateProvider(ABC):
    @abstractmethod
    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
        """Return current exchange rates for the given currency pairs."""


@dataclass(frozen=True)
class SymbolLookupResult:
    symbol: str
    name: str
    market: str
    sector: str | None = None


class SymbolLookupProvider(ABC):
    @abstractmethod
    def search(
        self,
        query: str,
        market: str | None = None,
    ) -> list[SymbolLookupResult]:
        """Return symbols matching the given symbol or company name query."""


@dataclass(frozen=True)
class ValuationResult:
    per: Decimal | None
    forward_per: Decimal | None
    psr: Decimal | None
    pbr: Decimal | None
    ev_ebitda: Decimal | None
    peg: Decimal | None
    fcf_yield: Decimal | None
    as_of: date
    source: str


class ValuationProvider(ABC):
    @abstractmethod
    def get_valuation(self, symbol: str, market: str) -> ValuationResult | None:
        """Return the current valuation metrics, or None when unavailable."""


@dataclass(frozen=True)
class EarningsReportResult:
    period_end: date
    revenue: Decimal | None
    operating_income: Decimal | None
    eps: Decimal | None
    eps_estimate: Decimal | None
    source: str


class EarningsProvider(ABC):
    @abstractmethod
    def get_quarterly_earnings(
        self, symbol: str, market: str
    ) -> list[EarningsReportResult]:
        """Return up to eight recent quarterly earnings reports."""
