from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class RawNewsEventCreate(BaseModel):
    title: str = Field(max_length=500)
    url: str = Field(max_length=2048)
    symbol: str | None = Field(default=None, max_length=20)
    market: str | None = Field(default=None, max_length=20)
    body: str | None = None
    source: str = Field(max_length=100)
    published_at: datetime | None = None
    collected_at: datetime | None = None
    payload: dict[str, Any] | None = None


class RawNewsEventResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    title: str
    url: str
    source: str
    published_at: UtcDatetime | None
    collected_at: UtcDatetime
    created_at: UtcDatetime
