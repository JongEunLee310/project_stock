from datetime import datetime

from pydantic import BaseModel


class ThesisCreate(BaseModel):
    asset_id: int
    summary: str
    risk_factors: str | None = None
    invalidation_conditions: str | None = None


class ThesisUpdate(BaseModel):
    summary: str | None = None
    risk_factors: str | None = None
    invalidation_conditions: str | None = None


class ThesisResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    asset_id: int
    summary: str
    risk_factors: str | None
    invalidation_conditions: str | None
    is_active: bool
    created_at: datetime
