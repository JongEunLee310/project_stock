from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.domains.alert_candidates.types import (
    AlertCandidateType,
    AlertImportance,
)


class AlertCandidateCreate(BaseModel):
    user_id: int
    candidate_type: AlertCandidateType
    importance: AlertImportance
    title: str
    message: str | None = None
    asset_id: int | None = None
    evidence: dict[str, Any] | None = None


class AlertCandidateResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    candidate_type: str
    importance: str
    status: str
    title: str
    message: str | None
    asset_id: int | None
    evidence: dict[str, Any] | None
    created_at: datetime
