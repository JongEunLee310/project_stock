from datetime import datetime
from enum import Enum

from pydantic import BaseModel

from app.adapters.llm.types import LLMTaskType


class DataQualityStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"
    PARTIAL = "partial"
    DUPLICATE = "duplicate"
    LOW_TRUST = "low_trust"
    MISSING = "missing"


class DataQualitySection(BaseModel):
    price_data_status: DataQualityStatus
    news_data_status: DataQualityStatus
    portfolio_data_status: DataQualityStatus
    warnings: list[str]


class PriceSnapshot(BaseModel):
    close: float | None
    return_1d: float | None
    return_5d: float | None
    return_20d: float | None
    drawdown_from_52w_high: float | None
    volume_vs_20d_avg: float | None


class PortfolioContext(BaseModel):
    holding: bool
    weight: float | None
    avg_buy_price: float | None
    unrealized_return: float | None


class RecentNewsItem(BaseModel):
    title: str
    summary: str
    source: str
    published_at: datetime
    trust_level: str


class SignalItem(BaseModel):
    type: str
    severity: str
    reason: str


class SymbolCard(BaseModel):
    symbol: str
    market: str
    display_name: str
    price_snapshot: PriceSnapshot
    portfolio_context: PortfolioContext | None
    recent_news: list[RecentNewsItem]
    signals: list[SignalItem]


class PortfolioSummary(BaseModel):
    cash_ratio: float | None
    top_holding_weight: float | None
    concentration_risk: str


class RecentDecision(BaseModel):
    symbol: str
    decision_type: str
    reason: str
    created_at: datetime


class OutputContract(BaseModel):
    format: str = "json"
    required_fields: list[str]


class LLMContextBundle(BaseModel):
    task_type: LLMTaskType
    as_of: datetime
    user_intent: str
    symbols: list[str]
    data_quality: DataQualitySection
    symbol_cards: list[SymbolCard]
    portfolio_summary: PortfolioSummary | None
    user_rules: list[str]
    recent_decisions: list[RecentDecision]
    output_contract: OutputContract
