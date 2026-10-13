from enum import Enum


class KnowledgeKind(str, Enum):
    FILING_SECTION = "FILING_SECTION"


class FilingSection(str, Enum):
    BUSINESS = "BUSINESS"
    RISK_FACTORS = "RISK_FACTORS"
