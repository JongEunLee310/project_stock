from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawNewsEventCreate(BaseModel):
    title: str = Field(max_length=500)
    url: str = Field(max_length=2048)
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
    published_at: datetime | None
    collected_at: datetime
    created_at: datetime
