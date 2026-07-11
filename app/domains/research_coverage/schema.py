from enum import Enum

from pydantic import BaseModel

from app.core.schema import UtcDatetime


class CoverageAxisName(str, Enum):
    NEWS = "NEWS"
    PRICE = "PRICE"
    EARNINGS = "EARNINGS"
    VALUATION = "VALUATION"
    DISCLOSURE = "DISCLOSURE"


class CoverageStatus(str, Enum):
    COLLECTED = "COLLECTED"
    NOT_COLLECTED = "NOT_COLLECTED"


class CoverageAxis(BaseModel):
    axis: CoverageAxisName
    status: CoverageStatus
    last_collected_at: UtcDatetime | None
    item_count: int


class ResearchCoverageResponse(BaseModel):
    asset_id: int
    axes: list[CoverageAxis]
