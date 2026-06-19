from enum import Enum


class AlertCandidateType(str, Enum):
    NEWS_SURGE = "NEWS_SURGE"
    PRICE_MOVEMENT = "PRICE_MOVEMENT"
    DISCLOSURE = "DISCLOSURE"
    PORTFOLIO_CONCENTRATION = "PORTFOLIO_CONCENTRATION"
    BUY_CHECKLIST_REQUIRED = "BUY_CHECKLIST_REQUIRED"


class AlertImportance(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class AlertCandidateStatus(str, Enum):
    UNREAD = "UNREAD"
    READ = "READ"
    CONFIRMED = "CONFIRMED"
