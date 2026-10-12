from datetime import date, datetime
from typing import ClassVar, Literal

from pydantic import BaseModel, Field

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import SensitivityLevel


class BriefEvidenceProjection(BaseModel):
    id: str
    title: str
    source_name: str
    published_at: datetime | None
    excerpt: str


class BriefPrice(BaseModel):
    close: str
    change_pct: str | None
    volume_change_pct: str | None


class BriefUpcoming(BaseModel):
    kind: Literal["EARNINGS"] = "EARNINGS"
    date: date


class DailyBriefSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC

    symbol: str
    asset_name: str
    market: str
    brief_date: date
    new_items: list[BriefEvidenceProjection]
    past_context: list[BriefEvidenceProjection]
    price: BriefPrice | None
    upcoming: list[BriefUpcoming]


class BriefPoint(BaseModel):
    text: str
    citations: list[str]


class BriefChange(BriefPoint):
    kind: Literal["NEW", "CONTINUING", "FADED"]


class ItemClassification(BaseModel):
    item: str
    impact_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = "LOW"
    sentiment: Literal["POSITIVE", "NEUTRAL", "NEGATIVE"] = "NEUTRAL"


class DailyBriefResult(BaseModel):
    headline: str
    new_developments: list[BriefPoint] = Field(default_factory=list)
    changes: list[BriefChange] = Field(default_factory=list)
    risk_checks: list[BriefPoint] = Field(default_factory=list)
    item_classifications: list[ItemClassification] = Field(default_factory=list)
    limitations: str | None = None


class BriefEvidence(BriefEvidenceProjection):
    raw_news_event_id: int | None
    news_item_id: int | None
    source_url: str


class BriefStats(BaseModel):
    new_item_count: int = 0
    truncated_count: int = 0
    past_context_count: int = 0
    citation_corrections: int = 0


class DailyBriefContent(BaseModel):
    headline: str
    new_developments: list[BriefPoint] = Field(default_factory=list)
    changes: list[BriefChange] = Field(default_factory=list)
    risk_checks: list[BriefPoint] = Field(default_factory=list)
    limitations: str | None = None
    evidence: list[BriefEvidence] = Field(default_factory=list)
    price: BriefPrice | None = None
    upcoming: list[BriefUpcoming] = Field(default_factory=list)
    stats: BriefStats = Field(default_factory=BriefStats)
    no_news: bool = False


class DailyResearchResult(BaseModel):
    processed: int = 0
    skipped_no_news: int = 0
    failed: dict[int, str] = Field(default_factory=dict)
    llm_calls: int = 0
    signals_created: int = 0
    alerts_created: int = 0
