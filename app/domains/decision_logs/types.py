from enum import Enum


class TargetType(str, Enum):
    SYMBOL = "SYMBOL"
    PORTFOLIO = "PORTFOLIO"
    TOPIC = "TOPIC"
    SECTOR = "SECTOR"
    MARKET = "MARKET"


class DecisionType(str, Enum):
    WATCH = "WATCH"
    RESEARCH_REQUIRED = "RESEARCH_REQUIRED"
    HOLD = "HOLD"
    BUY_REVIEW = "BUY_REVIEW"
    SELL_REVIEW = "SELL_REVIEW"
    REDUCE_REVIEW = "REDUCE_REVIEW"
    REBALANCE_REVIEW = "REBALANCE_REVIEW"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    NO_ACTION = "NO_ACTION"


class DecisionStatus(str, Enum):
    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    REVIEW_DUE = "REVIEW_DUE"
    REVIEWED = "REVIEWED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"


class ConfidenceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceRelationship(str, Enum):
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    RISK = "RISK"
    BACKGROUND = "BACKGROUND"


class RiskSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class ReviewTriggerType(str, Enum):
    DATE = "DATE"
    PRICE = "PRICE"
    METRIC = "METRIC"
    EVENT = "EVENT"
    SIGNAL_CHANGE = "SIGNAL_CHANGE"
    MANUAL = "MANUAL"


class ReviewTriggerStatus(str, Enum):
    PENDING = "PENDING"
    TRIGGERED = "TRIGGERED"
    DISMISSED = "DISMISSED"


class CreatedBy(str, Enum):
    USER = "USER"
    AI = "AI"
    SYSTEM = "SYSTEM"


class OutcomeStatus(str, Enum):
    THESIS_CONFIRMED = "THESIS_CONFIRMED"
    THESIS_PARTIALLY_CONFIRMED = "THESIS_PARTIALLY_CONFIRMED"
    THESIS_INVALIDATED = "THESIS_INVALIDATED"
    INSUFFICIENT_TIME = "INSUFFICIENT_TIME"
    CLOSED = "CLOSED"


class ThesisResult(str, Enum):
    CONFIRMED = "CONFIRMED"
    PARTIALLY_CONFIRMED = "PARTIALLY_CONFIRMED"
    INVALIDATED = "INVALIDATED"
