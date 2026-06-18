from datetime import datetime

from pydantic import BaseModel, Field


class WatchlistCreate(BaseModel):
    name: str = Field(max_length=255)


class WatchlistResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    created_at: datetime


class WatchlistItemCreate(BaseModel):
    asset_id: int
    priority: int = 0


class WatchlistItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    watchlist_id: int
    asset_id: int
    priority: int
    created_at: datetime
