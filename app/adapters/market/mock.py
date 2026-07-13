from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from app.adapters.market.base import (
    EarningsEventResult,
    EarningsProvider,
    EarningsReportResult,
    ExchangeRateProvider,
    ExchangeRateResult,
    IndexQuoteProvider,
    IndexQuoteResult,
    MarketDataProvider,
    PriceBarResult,
    PriceSeriesProvider,
    QuoteResult,
    SymbolLookupProvider,
    SymbolLookupResult,
    ValuationProvider,
    ValuationResult,
)

_AS_OF = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)
_PRICE_SERIES_END_DATE = date(2026, 6, 25)
_VALUATION_AS_OF = date(2026, 7, 12)
_INTRADAY_BAR_COUNT = 26
_RANGE_COUNTS = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252,
    "5Y": 1260,
}
MARKET_INDEX_SYMBOLS = ["SPX", "IXIC", "KOSPI", "VIX"]
_SAMPLE_EXCHANGE_RATES: dict[str, ExchangeRateResult] = {
    "USD/KRW": ExchangeRateResult(
        pair="USD/KRW",
        rate=Decimal("1384.50"),
        change_percent=Decimal("0.18"),
        as_of=_AS_OF,
    ),
}
_INDEX_NAMES = {
    "SPX": "S&P 500",
    "IXIC": "NASDAQ Composite",
    "KOSPI": "KOSPI",
    "VIX": "VIX",
}
_SAMPLE_QUOTES: dict[str, QuoteResult] = {
    "AAPL": QuoteResult(
        symbol="AAPL",
        name="Apple Inc.",
        price=Decimal("195.64"),
        previous_close=Decimal("193.20"),
        change=Decimal("2.44"),
        change_percent=Decimal("1.26"),
        currency="USD",
        as_of=_AS_OF,
        per=Decimal("31.20"),
        peg=Decimal("2.45"),
        market_cap=Decimal("3000000000000"),
        next_earnings_date="2026-07-30",
        fifty_two_week_low=Decimal("164.08"),
        fifty_two_week_high=Decimal("237.49"),
        target_price=Decimal("220.00"),
        target_upside_percent=Decimal("12.45"),
    ),
    "TSLA": QuoteResult(
        symbol="TSLA",
        name="Tesla, Inc.",
        price=Decimal("182.31"),
        previous_close=Decimal("185.00"),
        change=Decimal("-2.69"),
        change_percent=Decimal("-1.45"),
        currency="USD",
        as_of=_AS_OF,
        market_cap=Decimal("580000000000"),
        next_earnings_date="2026-07-23",
    ),
}
_SYMBOL_LOOKUP_CATALOG = [
    SymbolLookupResult("AAPL", "Apple Inc.", "NASDAQ", "Technology"),
    SymbolLookupResult("MSFT", "Microsoft Corporation", "NASDAQ", "Technology"),
    SymbolLookupResult("GOOGL", "Alphabet Inc.", "NASDAQ", "Communication Services"),
    SymbolLookupResult("AMZN", "Amazon.com, Inc.", "NASDAQ", "Consumer Cyclical"),
    SymbolLookupResult("NVDA", "NVIDIA Corporation", "NASDAQ", "Technology"),
    SymbolLookupResult("TSLA", "Tesla, Inc.", "NASDAQ", "Consumer Cyclical"),
    SymbolLookupResult("META", "Meta Platforms, Inc.", "NASDAQ", "Communication Services"),
    SymbolLookupResult("JPM", "JPMorgan Chase & Co.", "NYSE", "Financial Services"),
    SymbolLookupResult("V", "Visa Inc.", "NYSE", "Financial Services"),
    SymbolLookupResult("JNJ", "Johnson & Johnson", "NYSE", "Healthcare"),
    SymbolLookupResult("005930", "Samsung Electronics Co., Ltd.", "KOSPI", "Technology"),
]


class MockMarketDataProvider(MarketDataProvider):
    def get_quote(self, symbols: list[str]) -> list[QuoteResult]:
        return [
            _SAMPLE_QUOTES.get(symbol.upper(), _fallback_quote(symbol))
            for symbol in symbols
        ]


class MockPriceSeriesProvider(PriceSeriesProvider):
    def get_daily_bars(
        self,
        symbol: str,
        market: str,
        range_value: str,
        adjusted: bool,
    ) -> list[PriceBarResult]:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        count = _RANGE_COUNTS.get(range_value, _RANGE_COUNTS["3M"])
        seed = _stable_seed(f"{normalized_symbol}:{normalized_market}")
        base_price = Decimal(seed % 50000 + 5000)
        dates = _business_days_ending_on(_PRICE_SERIES_END_DATE, count)

        bars: list[PriceBarResult] = []
        previous_close = base_price
        for index, trading_date in enumerate(dates):
            drift = Decimal(((seed + index * 17) % 900) - 450) / Decimal("100")
            open_price = _money(previous_close + drift)
            close_move = Decimal(((seed // 7 + index * 13) % 700) - 350) / Decimal(
                "100"
            )
            close_price = _money(max(open_price + close_move, Decimal("1.00")))
            spread = Decimal(((seed // 13 + index * 5) % 300) + 50) / Decimal("100")
            high_price = _money(max(open_price, close_price) + spread)
            low_price = _money(
                max(min(open_price, close_price) - spread, Decimal("0.01"))
            )
            adjusted_close_price = close_price
            if adjusted:
                factor_bps = Decimal(10000 - ((seed + index) % 35)) / Decimal("10000")
                adjusted_close_price = _money(close_price * factor_bps)
            volume = int((seed % 1_000_000) + 100_000 + index * 997)
            timestamp = datetime.combine(
                trading_date,
                time.min,
                tzinfo=timezone.utc,
            )
            bars.append(
                PriceBarResult(
                    symbol=normalized_symbol,
                    market=normalized_market,
                    interval="1d",
                    timestamp=timestamp,
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    adjusted_close_price=adjusted_close_price,
                    volume=volume,
                    currency=_currency_for_market(normalized_market),
                    source="mock",
                )
            )
            previous_close = close_price
        return bars

    def get_intraday_bars(
        self,
        symbol: str,
        market: str,
    ) -> list[PriceBarResult]:
        normalized_symbol = symbol.upper()
        normalized_market = market.upper()
        seed = _stable_seed(f"{normalized_symbol}:{normalized_market}:intraday")
        previous_close = Decimal(seed % 50000 + 5000)
        session_start = datetime.combine(
            _PRICE_SERIES_END_DATE,
            time(13, 30),
            tzinfo=timezone.utc,
        )

        bars: list[PriceBarResult] = []
        for index in range(_INTRADAY_BAR_COUNT):
            drift = Decimal(((seed + index * 17) % 300) - 150) / Decimal("100")
            open_price = _money(previous_close + drift)
            close_move = Decimal(((seed // 7 + index * 13) % 240) - 120) / Decimal(
                "100"
            )
            close_price = _money(max(open_price + close_move, Decimal("1.00")))
            spread = Decimal(((seed // 13 + index * 5) % 100) + 10) / Decimal(
                "100"
            )
            high_price = _money(max(open_price, close_price) + spread)
            low_price = _money(
                max(min(open_price, close_price) - spread, Decimal("0.01"))
            )
            bars.append(
                PriceBarResult(
                    symbol=normalized_symbol,
                    market=normalized_market,
                    interval="15m",
                    timestamp=session_start + timedelta(minutes=15 * index),
                    open_price=open_price,
                    high_price=high_price,
                    low_price=low_price,
                    close_price=close_price,
                    adjusted_close_price=close_price,
                    volume=int((seed % 100_000) + 10_000 + index * 97),
                    currency=_currency_for_market(normalized_market),
                    source="mock",
                )
            )
            previous_close = close_price
        return bars


class MockValuationProvider(ValuationProvider):
    def get_valuation(self, symbol: str, market: str) -> ValuationResult | None:
        seed = _stable_seed(f"{symbol.upper()}:{market.upper()}:valuation")
        deficit = seed % 5 == 0
        return ValuationResult(
            per=None if deficit else _ratio(seed, 9, 120, 10),
            forward_per=None if deficit else _ratio(seed, 7, 100, 10),
            psr=_ratio(seed, 1, 80, 10),
            pbr=_ratio(seed, 1, 60, 10),
            ev_ebitda=None if seed % 7 == 0 else _ratio(seed, 5, 150, 10),
            peg=None if seed % 3 == 0 else _ratio(seed, 1, 40, 10),
            fcf_yield=_ratio(seed, -50, 150, 10),
            as_of=_VALUATION_AS_OF,
            source="mock",
        )


class MockEarningsProvider(EarningsProvider):
    def get_quarterly_earnings(
        self, symbol: str, market: str
    ) -> list[EarningsReportResult]:
        period_ends = [
            date(2024, 9, 30),
            date(2024, 12, 31),
            date(2025, 3, 31),
            date(2025, 6, 30),
            date(2025, 9, 30),
            date(2025, 12, 31),
            date(2026, 3, 31),
            date(2026, 6, 30),
        ]
        reports: list[EarningsReportResult] = []
        for index, period_end in enumerate(period_ends):
            revenue = Decimal(90000 + index * 2500)
            eps = Decimal("1.20") + Decimal(index) * Decimal("0.08")
            estimate = (
                None
                if index == 5
                else eps + (Decimal("0.05") if index % 2 else Decimal("-0.04"))
            )
            reports.append(
                EarningsReportResult(
                    period_end=period_end,
                    revenue=revenue,
                    operating_income=revenue * Decimal("0.28"),
                    eps=eps,
                    eps_estimate=estimate,
                    source="mock",
                )
            )
        return list(reversed(reports))

    def get_earnings_events(
        self, symbol: str, market: str
    ) -> list[EarningsEventResult]:
        event_dates = [
            date(2024, 7, 25),
            date(2024, 10, 24),
            date(2025, 1, 30),
            date(2025, 4, 24),
            date(2025, 7, 31),
            date(2025, 10, 30),
            date(2026, 1, 29),
            date(2026, 4, 30),
            date.today() + timedelta(days=30),
        ]
        events: list[EarningsEventResult] = []
        for index, event_date in enumerate(event_dates):
            actual = Decimal("1.20") + Decimal(index) * Decimal("0.08")
            events.append(
                EarningsEventResult(
                    event_date=event_date,
                    eps_actual=None if index == 2 else actual,
                    eps_estimate=(
                        None
                        if index == 5
                        else actual
                        + (
                            Decimal("0.05")
                            if index % 2
                            else Decimal("-0.04")
                        )
                    ),
                    source="mock",
                )
            )
        return events


class MockIndexQuoteProvider(IndexQuoteProvider):
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
        return [_index_quote(symbol) for symbol in symbols]


class MockExchangeRateProvider(ExchangeRateProvider):
    def get_rates(self, pairs: list[str]) -> list[ExchangeRateResult]:
        return [
            rate
            for pair in pairs
            if (rate := _SAMPLE_EXCHANGE_RATES.get(pair.upper())) is not None
        ]


class MockSymbolLookupProvider(SymbolLookupProvider):
    def search(
        self,
        query: str,
        market: str | None = None,
    ) -> list[SymbolLookupResult]:
        normalized_query = query.strip().upper()
        normalized_market = market.strip().upper() if market is not None else None
        if not normalized_query:
            return []

        return [
            item
            for item in _SYMBOL_LOOKUP_CATALOG
            if (normalized_market is None or item.market == normalized_market)
            and (
                normalized_query in item.symbol.upper()
                or normalized_query in item.name.upper()
            )
        ]


def _fallback_quote(symbol: str) -> QuoteResult:
    normalized_symbol = symbol.upper()
    seed = sum(ord(character) for character in normalized_symbol)
    price = Decimal(seed % 200 + 50)
    previous_close = price - Decimal("1.00")
    return QuoteResult(
        symbol=normalized_symbol,
        name=f"{normalized_symbol} Mock Asset",
        price=price,
        previous_close=previous_close,
        change=price - previous_close,
        change_percent=Decimal("1.00"),
        currency="USD",
        as_of=_AS_OF,
    )


def _index_quote(symbol: str) -> IndexQuoteResult:
    normalized_symbol = symbol.upper()
    seed = _stable_seed(f"index:{normalized_symbol}")
    value = _money(Decimal(seed % 900_000 + 1_000) / Decimal("100"))
    change_percent = _money(
        Decimal((seed // 17) % 1000 - 500) / Decimal("100")
    )
    return IndexQuoteResult(
        symbol=normalized_symbol,
        name=_INDEX_NAMES.get(normalized_symbol, f"{normalized_symbol} Index"),
        value=value,
        change_percent=change_percent,
        reference_at=_AS_OF,
    )


def _business_days_ending_on(end_date: date, count: int) -> list[date]:
    days: list[date] = []
    current = end_date
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current -= timedelta(days=1)
    return list(reversed(days))


def _stable_seed(value: str) -> int:
    return int(sha256(value.encode("utf-8")).hexdigest()[:12], 16)


def _ratio(seed: int, minimum: int, span: int, scale: int) -> Decimal:
    return Decimal(minimum + seed % span) / Decimal(scale)


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _currency_for_market(market: str) -> str:
    if market == "KRX":
        return "KRW"
    return "USD"
