from datetime import datetime, timezone
from decimal import Decimal

from app.adapters.market.base import MarketDataProvider, QuoteResult

_AS_OF = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)
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
