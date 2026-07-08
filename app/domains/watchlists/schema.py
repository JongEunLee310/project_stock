from decimal import Decimal

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


class WatchlistCreate(BaseModel):
    name: str = Field(max_length=255)


class WatchlistResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    created_at: UtcDatetime


class WatchlistItemCreate(BaseModel):
    asset_id: int
    priority: int = 0
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None


class WatchlistItemResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    watchlist_id: int
    asset_id: int
    priority: int
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None
    created_at: UtcDatetime


class AssetBriefResponse(BaseModel):
    symbol: str
    market: str
    name: str
    price: str
    change_percent: str
    sector: str | None = None
    currency: str | None = None
    reference_at: UtcDatetime | None = None


class WatchlistItemExpandedResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    watchlist_id: int
    asset_id: int
    priority: int
    reason: str | None = None
    tags: list[str] = Field(default_factory=list)
    memo: str | None = None
    created_at: UtcDatetime
    status: str
    asset: AssetBriefResponse | None = None


class SparklineBar(BaseModel):
    date: str
    close: str


class AssetSparklineResponse(BaseModel):
    symbol: str
    bars: list[SparklineBar]


class WatchlistSparklineResponse(BaseModel):
    items: list[AssetSparklineResponse]


class RecentWatchlistItemResponse(BaseModel):
    symbol: str
    name: str
    created_at: UtcDatetime


class BuyReadinessProjection(BaseModel):
    level: str
    level_label: str
    cash_weight: Decimal
    buy_candidate_count: int
    message: str


class WatchlistSummaryResponse(BaseModel):
    total_count: int
    risk_increasing_count: int
    recent_items: list[RecentWatchlistItemResponse]
    buy_readiness: BuyReadinessProjection | None


class WatchlistSummaryTrendDataPoint(BaseModel):
    date: str
    count: int


class WatchlistSummaryTrendSeries(BaseModel):
    key: str
    data: list[WatchlistSummaryTrendDataPoint]


class WatchlistSummaryTrendResponse(BaseModel):
    days: int
    series: list[WatchlistSummaryTrendSeries]


class WatchlistObservationItemResponse(BaseModel):
    symbol: str
    note: str


class WatchlistObservationsResponse(BaseModel):
    summary: str
    items: list[WatchlistObservationItemResponse]
    generated_at: UtcDatetime


class WatchlistItemEvaluationProjection(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str


class WatchlistEvaluationsResponse(BaseModel):
    items: list[WatchlistItemEvaluationProjection]
    needs_research_count: int
    generated_at: UtcDatetime


class WatchlistAlertRuleTemplateProjection(BaseModel):
    template_type: str
    label: str
    condition_description: str
    is_active: bool


class WatchlistAlertRuleTemplateApply(BaseModel):
    template_type: str
    is_active: bool


class WatchlistAlertRuleTemplateBulkRequest(BaseModel):
    templates: list[WatchlistAlertRuleTemplateApply]


class StockRecommendationProjection(BaseModel):
    symbol: str
    name: str
    rationale: str
    reference_metrics: list[str]


class WatchlistRecommendationsResponse(BaseModel):
    recommendations: list[StockRecommendationProjection]
    generated_at: UtcDatetime
