from enum import Enum


class ThesisVerdict(str, Enum):
    CHALLENGED = "CHALLENGED"
    MIXED = "MIXED"
    SUPPORTED = "SUPPORTED"
    NO_RELEVANT_EVIDENCE = "NO_RELEVANT_EVIDENCE"


class FindingRelation(str, Enum):
    CHALLENGES = "CHALLENGES"
    SUPPORTS = "SUPPORTS"


class FindingAspect(str, Enum):
    THESIS = "THESIS"
    RATIONALE = "RATIONALE"
    RISK = "RISK"
