from decimal import Decimal
from enum import Enum

from pydantic import BaseModel, Field


class ValuationProfile(str, Enum):
    FINANCIAL = "FINANCIAL"
    HIGH_GROWTH = "HIGH_GROWTH"
    DEFICIT = "DEFICIT"
    DIVIDEND = "DIVIDEND"
    GENERAL = "GENERAL"


class ValuationMetricName(str, Enum):
    PER = "PER"
    FORWARD_PER = "FORWARD_PER"
    PSR = "PSR"
    PBR = "PBR"
    EV_EBITDA = "EV_EBITDA"
    PEG = "PEG"
    FCF_YIELD = "FCF_YIELD"


class ValuationMetric(BaseModel):
    metric: ValuationMetricName
    value: Decimal | None
    five_year_median: Decimal | None
    percentile: int | None = Field(default=None, ge=0, le=100)


class ValuationMetricsResponse(BaseModel):
    asset_id: int
    profile: ValuationProfile
    highlighted_metrics: list[ValuationMetricName]
    metrics: list[ValuationMetric]
