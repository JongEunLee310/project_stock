from decimal import Decimal

from pydantic import BaseModel

from app.core.schema import UtcDatetime


class DashboardSummaryResponse(BaseModel):
    risk_alert_count: int
    important_news_count: int
    review_signal_count: int
    cash_weight: str | None

    # 히스토리 스냅샷 도입 시 계산(후속)
    risk_alert_delta: Decimal | None = None
    important_news_delta: Decimal | None = None
    review_signal_delta: Decimal | None = None
    cash_weight_delta: Decimal | None = None


class DashboardBriefingResponse(BaseModel):
    headline: str
    body: str
    risk_headline: str | None = None
    risk_checks: list[str]
    generated_at: UtcDatetime
