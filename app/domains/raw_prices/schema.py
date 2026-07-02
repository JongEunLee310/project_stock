from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class RawPriceCreate(BaseModel):
    symbol: str = Field(max_length=20)
    market: str = Field(max_length=20)
    interval: str = Field(max_length=10)
    source: str = Field(max_length=30)
    payload: dict[str, Any]
    payload_hash: str = Field(max_length=64)
    fetched_at: datetime | None = None


class RawPriceResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str
    market: str
    interval: str
    source: str
    payload_hash: str
    fetched_at: UtcDatetime
