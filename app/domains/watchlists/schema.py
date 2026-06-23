from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class WatchlistCreate(BaseModel):
    name: str = Field(max_length=255)


class WatchlistResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    created_at: UtcDatetime


class WatchlistItemCreate(BaseModel):
    asset_id: int
    priority: int = 0
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None


class WatchlistItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    watchlist_id: int
    asset_id: int
    priority: int
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None
    created_at: UtcDatetime


class AssetBriefResponse(BaseModel):
    symbol: str
    name: str
    price: str
    change_percent: str
    sector: str | None = None


class WatchlistItemExpandedResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    watchlist_id: int
    asset_id: int
    priority: int
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None
    created_at: UtcDatetime
    asset: AssetBriefResponse | None = None
