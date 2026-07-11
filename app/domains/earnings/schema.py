from decimal import Decimal

from pydantic import BaseModel


class EarningsQuarter(BaseModel):
    period: str
    revenue: Decimal
    operating_income: Decimal
    eps: Decimal
    revenue_yoy_percent: Decimal | None
    operating_margin_percent: Decimal
    eps_estimate: Decimal | None
    eps_surprise_percent: Decimal | None


class SegmentGrowth(BaseModel):
    name: str
    revenue_share_percent: Decimal
    yoy_growth_percent: Decimal


class EarningsSummaryResponse(BaseModel):
    asset_id: int
    quarters: list[EarningsQuarter]
    guidance: str | None
    segments: list[SegmentGrowth]
