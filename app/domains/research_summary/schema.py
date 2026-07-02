from pydantic import BaseModel

from app.core.schema import UtcDatetime


class ResearchRisk(BaseModel):
    id: str
    title: str
    level: str
    description: str


class ResearchSummaryResponse(BaseModel):
    asset_id: int
    stance: str
    stance_confidence: str
    headline: str
    body: str
    key_risks: list[ResearchRisk]
    created_at: UtcDatetime
