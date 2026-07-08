from enum import Enum


class NewsRisk(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ValuationBurden(str, Enum):
    HIGH = "HIGH"
    MODERATE = "MODERATE"
    LOW = "LOW"


class ThemeHeat(str, Enum):
    OVERHEATED = "OVERHEATED"
    NEUTRAL = "NEUTRAL"
    COLD = "COLD"


class AiJudgment(str, Enum):
    RISK_INCREASING = "RISK_INCREASING"
    WATCH = "WATCH"
    STABLE = "STABLE"


class BuyReadinessLevel(str, Enum):
    SUFFICIENT = "SUFFICIENT"
    LIMITED = "LIMITED"
    RESTRICTED = "RESTRICTED"


class WatchlistAlertTemplateType(str, Enum):
    PRICE_SPIKE = "PRICE_SPIKE"
    NEWS_RISK_HIGH = "NEWS_RISK_HIGH"
    AI_JUDGMENT_CHANGE = "AI_JUDGMENT_CHANGE"
    THEME_OVERHEAT = "THEME_OVERHEAT"
