from pydantic import BaseModel

from app.domains.research_summary.schema import CounterPoint, ResearchRisk


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


class ResearchSummaryResult(BaseModel):
    stance: str
    stance_confidence: str
    stance_comment: str | None = None
    headline: str
    body: str
    positive_factors: list[str]
    caution_factors: list[str]
    next_checks: list[str]
    counter_points: list[CounterPoint]
    confidence_basis: str | None = None
    key_risks: list[ResearchRisk]


class ItemEvaluationResult(BaseModel):
    symbol: str
    news_risk: str
    valuation_burden: str
    theme_heat: str
    ai_judgment: str


class WatchlistEvaluationsResult(BaseModel):
    items: list[ItemEvaluationResult]
