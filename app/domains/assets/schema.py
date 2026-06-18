from datetime import datetime

from pydantic import BaseModel, Field


class AssetCreate(BaseModel):
    symbol: str = Field(max_length=20)
    name: str = Field(max_length=255)
    market: str = Field(max_length=20)


class AssetResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    symbol: str
    name: str
    market: str
    is_active: bool
    created_at: datetime
