from datetime import datetime, timezone

from app.adapters.disclosure.base import DisclosureProvider, DisclosureResult

_PUBLISHED_AT = datetime(2026, 6, 19, 0, 0, tzinfo=timezone.utc)


class MockDisclosureProvider(DisclosureProvider):
    def fetch(self, symbols: list[str]) -> list[DisclosureResult]:
        return [
            _disclosure_for(symbol, index)
            for index, symbol in enumerate(symbols, start=1)
        ]


def _disclosure_for(symbol: str, index: int) -> DisclosureResult:
    normalized_symbol = symbol.upper()
    return DisclosureResult(
        symbol=normalized_symbol,
        title=f"{normalized_symbol} mock disclosure {index}",
        url=f"https://example.com/mock-disclosures/{normalized_symbol.lower()}/{index}",
        source="mock",
        published_at=_PUBLISHED_AT,
        payload={"symbol": normalized_symbol, "index": index},
    )
