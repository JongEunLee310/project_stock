from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class ResearchStatus(str, Enum):
    ANALYZED = "ANALYZED"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"
    COLLECTING = "COLLECTING"
    INSUFFICIENT = "INSUFFICIENT"
    STALE = "STALE"
    PENDING_ANALYSIS = "PENDING_ANALYSIS"


class ResearchQueueFilter(str, Enum):
    NEEDS_RESEARCH = "needs_research"
    RISK_INCREASING = "risk_increasing"
    EARNINGS_UPCOMING = "earnings_upcoming"
    RECENTLY_UPDATED = "recently_updated"


class ResearchQueueItemProjection(BaseModel):
    asset_id: int
    symbol: str
    name: str
    market: str
    research_status: ResearchStatus
    completeness_pct: int = Field(ge=0, le=100)
    stance: str | None
    headline: str | None
    key_issue: str | None
    last_updated_at: UtcDatetime | None
    signal_type: str | None


class ResearchQueueSummaryProjection(BaseModel):
    total_research_count: int
    needs_attention_count: int
    updated_today_count: int
    insufficient_count: int


class ResearchQueueData(BaseModel):
    summary: ResearchQueueSummaryProjection
    items: list[ResearchQueueItemProjection]


@dataclass(frozen=True)
class ResearchDataPresence:
    has_news: bool = False
    has_price: bool = False
    has_earnings: bool = False
    has_valuation: bool = False
    latest_news_at: datetime | None = None
    latest_report_at: datetime | None = None
    latest_signal_at: datetime | None = None
