from decimal import Decimal

from pydantic import BaseModel

from app.core.schema import UtcDatetime


class MarketIndexQuoteResponse(BaseModel):
    symbol: str
    name: str
    value: Decimal
    change_percent: Decimal
    reference_at: UtcDatetime
