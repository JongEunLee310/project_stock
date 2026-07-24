from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ThesisConflictResult(BaseModel):
    status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"]
    reason: str
    invalidation_triggered: bool


class ThesisConflictAnalysisResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    news_item_id: int
    thesis_id: int
    status: str
    reason: str
    invalidation_triggered: bool
    created_at: datetime
