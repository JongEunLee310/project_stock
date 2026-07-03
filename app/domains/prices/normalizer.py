from datetime import UTC, datetime


class PriceNormalizer:
    def canonicalize_symbol(self, symbol: str) -> str:
        return symbol.upper()

    def canonicalize_market(self, market: str) -> str:
        return market.upper()

    def normalize_timestamp(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
