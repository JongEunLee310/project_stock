from pydantic import BaseModel

from app.core.schema import UtcDatetime


class PriceBar(BaseModel):
    date: str
    open: str
    high: str
    low: str
    close: str
    adjusted_close: str
    volume: int


class PriceSeriesResponse(BaseModel):
    symbol: str
    market: str
    currency: str
    interval: str
    range: str
    source: str
    last_updated_at: UtcDatetime
    bars: list[PriceBar]
