from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from app.adapters.market.base import (
    IndexQuoteProvider,
    IndexQuoteResult,
    MarketDataProvider,
    PriceBarResult,
    PriceSeriesProvider,
    QuoteResult,
)

_AS_OF = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)
_PRICE_SERIES_END_DATE = date(2026, 6, 25)
_RANGE_COUNTS = {
    "1M": 22,
    "3M": 66,
    "6M": 132,
    "1Y": 252,
}
MARKET_INDEX_SYMBOLS = ["SPX", "IXIC", "KOSPI", "VIX"]
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
    ),
}


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


class MockIndexQuoteProvider(IndexQuoteProvider):
    def get_quotes(self, symbols: list[str]) -> list[IndexQuoteResult]:
        return [_index_quote(symbol) for symbol in symbols]


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


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _currency_for_market(market: str) -> str:
    if market == "KRX":
        return "KRW"
    return "USD"
