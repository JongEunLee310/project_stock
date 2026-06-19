from datetime import datetime

from pydantic import BaseModel, Field


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
    is_active: bool
    created_at: datetime


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
    as_of: datetime
