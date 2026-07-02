from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class AssetCreate(BaseModel):
    symbol: str = Field(max_length=20)
    name: str = Field(max_length=255)
    market: str = Field(max_length=20)
    sector: str | None = Field(default=None, max_length=100)
    industry: str | None = Field(default=None, max_length=100)
    description: str | None = None


class AssetResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str
    name: str
    market: str
    sector: str | None = None
    is_active: bool
    created_at: UtcDatetime


class AssetDetailResponse(BaseModel):
    id: int
    symbol: str
    name: str
    market: str
    price: str
    previous_close: str
    change: str
    change_percent: str
    currency: str
    sector: str | None = None
    industry: str | None = None
    description: str | None = None
    updated_at: UtcDatetime
    market_cap: str | None = None
    next_earnings_date: str | None = None
    per: str | None = None
    peg: str | None = None
    fifty_two_week_low: str | None = None
    fifty_two_week_high: str | None = None
    target_price: str | None = None
    target_upside_percent: str | None = None
