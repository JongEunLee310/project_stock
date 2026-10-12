from datetime import date, datetime
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import SensitivityLevel


def _retain_invalid_id(value: Any, handler: ValidatorFunctionWrapHandler) -> str:
    # Advertise strict patterns to structured-output providers, but retain malformed
    # strings for validate_brief_citations to remove and count after parsing.
    try:
        return str(handler(value))
    except ValidationError as exc:
        if isinstance(value, str) and all(
            error["type"] == "string_pattern_mismatch" for error in exc.errors()
        ):
            return value
        raise


NewEvidenceId = Annotated[
    str, Field(pattern=r"^N\d+$"), WrapValidator(_retain_invalid_id)
]
EvidenceId = Annotated[
    str, Field(pattern=r"^[NP]\d+$"), WrapValidator(_retain_invalid_id)
]


class BriefEvidenceProjection(BaseModel):
    id: str
    title: str
    source_name: str
    published_at: datetime | None
    excerpt: str


class BriefPrice(BaseModel):
    as_of: date
    stale: bool
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
    citations: list[NewEvidenceId]


class BriefChange(BriefPoint):
    citations: list[EvidenceId]
    kind: Literal["NEW", "CONTINUING", "FADED"]


class ItemClassification(BaseModel):
    item: NewEvidenceId
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
