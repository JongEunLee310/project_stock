from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class ResearchRisk(BaseModel):
    id: str
    title: str
    level: str
    description: str
    evidence: list[str] = Field(default_factory=list)


class ResearchSummaryResponse(BaseModel):
    asset_id: int
    stance: str
    stance_confidence: str
    stance_comment: str | None = None
    headline: str
    body: str
    positive_factors: list[str] = Field(default_factory=list)
    caution_factors: list[str] = Field(default_factory=list)
    next_checks: list[str] = Field(default_factory=list)
    confidence_basis: str | None = None
    key_risks: list[ResearchRisk]
    created_at: UtcDatetime
