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
