from enum import Enum


class DocumentType(str, Enum):
    NEWS = "NEWS"
    DISCLOSURE = "DISCLOSURE"
    EARNINGS = "EARNINGS"
    ANALYST_REPORT = "ANALYST_REPORT"
    COMMUNITY = "COMMUNITY"
    COMPANY_IR = "COMPANY_IR"


class ProcessingStatus(str, Enum):
    PENDING = "PENDING"
    NORMALIZED = "NORMALIZED"
    EXTRACTED = "EXTRACTED"
    FAILED = "FAILED"


class EventType(str, Enum):
    EARNINGS_GUIDANCE = "EARNINGS_GUIDANCE"
    BUYBACK = "BUYBACK"
    REGULATION = "REGULATION"
    SUPPLY_CONTRACT = "SUPPLY_CONTRACT"
    MANAGEMENT_CHANGE = "MANAGEMENT_CHANGE"
    ACCOUNTING_ISSUE = "ACCOUNTING_ISSUE"
    PRODUCTION_DISRUPTION = "PRODUCTION_DISRUPTION"
    OTHER = "OTHER"


class SentimentDirection(str, Enum):
    POSITIVE = "POSITIVE"
    NEUTRAL = "NEUTRAL"
    NEGATIVE = "NEGATIVE"
    MIXED = "MIXED"


class ImportanceLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EvidenceRole(str, Enum):
    PRIMARY = "PRIMARY"
    SUPPORTING = "SUPPORTING"
    CONTRADICTING = "CONTRADICTING"
    BACKGROUND = "BACKGROUND"


class LifecycleStatus(str, Enum):
    EMERGING = "EMERGING"
    RISING = "RISING"
    ACTIVE = "ACTIVE"
    COOLING = "COOLING"
    ARCHIVED = "ARCHIVED"


class EventStatus(str, Enum):
    ACTIVE = "ACTIVE"
    MERGED = "MERGED"
    DISMISSED = "DISMISSED"


class TopicCategory(str, Enum):
    GROWTH = "GROWTH"
    REGULATION = "REGULATION"
    EARNINGS = "EARNINGS"
    DEMAND = "DEMAND"
    MARKET_EVENT = "MARKET_EVENT"
    CAPITAL_POLICY = "CAPITAL_POLICY"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"


class SymbolRelationship(str, Enum):
    DIRECT = "DIRECT"
    SUPPLY_CHAIN = "SUPPLY_CHAIN"
    COMPETITOR = "COMPETITOR"
    CUSTOMER = "CUSTOMER"


class InvestorType(str, Enum):
    FOREIGN = "FOREIGN"
    INSTITUTION = "INSTITUTION"
    RETAIL = "RETAIL"
    ETF = "ETF"


class MarketEventKind(str, Enum):
    EARNINGS = "EARNINGS"
    IR_EVENT = "IR_EVENT"
    POLICY = "POLICY"
    RATE_DECISION = "RATE_DECISION"
    SHAREHOLDER_MEETING = "SHAREHOLDER_MEETING"
    PRODUCT_EVENT = "PRODUCT_EVENT"
    REGULATION = "REGULATION"
    LOCKUP_EXPIRY = "LOCKUP_EXPIRY"
    OTHER = "OTHER"


class ValuationBurden(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AgentStage(str, Enum):
    COLLECT = "COLLECT"
    NORMALIZE = "NORMALIZE"
    EXTRACT = "EXTRACT"
    CLUSTER = "CLUSTER"
    SENTIMENT = "SENTIMENT"
    IMPACT = "IMPACT"
    LINK = "LINK"


class AgentRunStatus(str, Enum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    DELAYED = "DELAYED"
    FAILED = "FAILED"


class FlowDirection(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    NEUTRAL = "NEUTRAL"


class ScenarioKind(str, Enum):
    OPTIMISTIC = "OPTIMISTIC"
    BASE = "BASE"
    CONSERVATIVE = "CONSERVATIVE"


class FundFlowDirection(str, Enum):
    INFLOW = "INFLOW"
    OUTFLOW = "OUTFLOW"
    NEUTRAL = "NEUTRAL"


class FlowLikelihood(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
