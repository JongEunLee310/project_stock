from enum import Enum


class AlertRuleSource(str, Enum):
    SYSTEM = "SYSTEM"
    USER = "USER"


class AlertTargetType(str, Enum):
    SYMBOL = "SYMBOL"
    WATCHLIST = "WATCHLIST"
    PORTFOLIO = "PORTFOLIO"
    TOPIC = "TOPIC"
    MARKET = "MARKET"


class AlertMetric(str, Enum):
    NEWS_RISK = "NEWS_RISK"
    PRICE_CHANGE_1D = "PRICE_CHANGE_1D"
    SIGNAL_CHANGED = "SIGNAL_CHANGED"
    AI_JUDGMENT_CHANGED = "AI_JUDGMENT_CHANGED"
    THEME_HEAT = "THEME_HEAT"
    POSITION_WEIGHT = "POSITION_WEIGHT"
    EARNINGS_DATE = "EARNINGS_DATE"
    TOPIC_IMPACT_SCORE = "TOPIC_IMPACT_SCORE"


class AlertOperator(str, Enum):
    EQ = "EQ"
    GTE = "GTE"
    LTE = "LTE"
    CHANGED = "CHANGED"


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertChannel(str, Enum):
    APP = "APP"
    EMAIL = "EMAIL"
    DISCORD = "DISCORD"
    SLACK = "SLACK"


class AlertDeliveryPolicy(str, Enum):
    ONCE_PER_TRANSITION = "ONCE_PER_TRANSITION"
    ONCE_PER_DAY = "ONCE_PER_DAY"


class AlertTemplateType(str, Enum):
    HOLDING_NEWS_RISK = "HOLDING_NEWS_RISK"
    WATCHLIST_AI_JUDGMENT = "WATCHLIST_AI_JUDGMENT"
    EARNINGS_D3 = "EARNINGS_D3"
    POSITION_WEIGHT_OVER = "POSITION_WEIGHT_OVER"
    NEWS_RISK_HIGH = "NEWS_RISK_HIGH"
    TOPIC_IMPACT_SURGE = "TOPIC_IMPACT_SURGE"
