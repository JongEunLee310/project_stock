from enum import Enum


class ReportType(str, Enum):
    ARTICLE = "ARTICLE"
    DAILY_BRIEF = "DAILY_BRIEF"
    FILING_ANALYSIS = "FILING_ANALYSIS"
