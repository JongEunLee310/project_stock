from pydantic import BaseModel


class BriefingResult(BaseModel):
    headline: str
    body: str
    risk_headline: str | None = None
    risk_checks: list[str]


class ObservationItem(BaseModel):
    symbol: str
    note: str


class ObservationsResult(BaseModel):
    summary: str
    items: list[ObservationItem]


class RecommendationItem(BaseModel):
    symbol: str
    rationale: str
    reference_metrics: list[str]


class StockRecommendationResult(BaseModel):
    recommendations: list[RecommendationItem]


class ItemEvaluationResult(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str


class WatchlistEvaluationsResult(BaseModel):
    items: list[ItemEvaluationResult]
