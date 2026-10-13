from datetime import date
from typing import Annotated, Any, ClassVar, Literal

from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    ValidatorFunctionWrapHandler,
    WrapValidator,
)

from app.adapters.llm.privacy import CloudSafePayload
from app.adapters.llm.types import SensitivityLevel


class ParagraphChange(BaseModel):
    id: str
    text: str


class ChangedSpan(BaseModel):
    old_tokens: list[str]
    new_tokens: list[str]


class ModifiedParagraph(BaseModel):
    id: str
    old_text: str
    new_text: str
    changed_spans: list[ChangedSpan]


class DiffStats(BaseModel):
    unchanged: int = 0
    modified: int = 0
    trivial: int = 0
    added: int = 0
    removed: int = 0
    added_chars: int = 0
    removed_chars: int = 0
    modified_chars: int = 0


class SectionDiff(BaseModel):
    section: str | None = None
    added: list[ParagraphChange] = Field(default_factory=list)
    removed: list[ParagraphChange] = Field(default_factory=list)
    modified: list[ModifiedParagraph] = Field(default_factory=list)
    stats: DiffStats = Field(default_factory=DiffStats)


Importance = Literal["LOW", "MEDIUM", "HIGH"]
FilingSection = Literal["BUSINESS", "RISK_FACTORS"]


def _retain_invalid_id(value: Any, handler: ValidatorFunctionWrapHandler) -> str:
    try:
        return str(handler(value))
    except ValidationError as exc:
        if isinstance(value, str) and all(
            error["type"] == "string_pattern_mismatch" for error in exc.errors()
        ):
            return value
        raise


CitationId = Annotated[
    str, Field(pattern=r"^[ARM]\d+$"), WrapValidator(_retain_invalid_id)
]


class ModifiedProjection(BaseModel):
    id: str
    old_text: str
    new_text: str


class FilingDiffSnapshot(CloudSafePayload):
    sensitivity: ClassVar[SensitivityLevel] = SensitivityLevel.PUBLIC
    free_text_fields: ClassVar[tuple[str, ...]] = ()

    symbol: str
    asset_name: str
    section: FilingSection
    old_fiscal_year: int
    new_fiscal_year: int
    added: list[ParagraphChange]
    removed: list[ParagraphChange]
    modified: list[ModifiedProjection]
    stats: DiffStats
    truncated_count: int = 0


class FilingChange(BaseModel):
    kind: Literal[
        "NEW_RISK",
        "REMOVED_RISK",
        "ESCALATED_RISK",
        "SOFTENED_RISK",
        "BUSINESS_CHANGE",
        "OTHER",
    ]
    title: str
    summary: str
    importance: Importance
    citations: list[CitationId]


class FilingSectionAnalysis(BaseModel):
    headline: str
    changes: list[FilingChange] = Field(default_factory=list)
    limitations: str | None = None


class FilingSectionContent(BaseModel):
    headline: str = ""
    changes: list[FilingChange] = Field(default_factory=list)
    limitations: str | None = None
    diff_stats: DiffStats = Field(default_factory=DiffStats)
    citation_corrections: int = 0
    truncated_count: int = 0
    failed: str | None = None


class FilingReference(BaseModel):
    accession: str
    fiscal_year: int
    filed_date: date | None
    source_url: str
    knowledge_document_id: dict[str, int]


class FilingEvidence(BaseModel):
    old_text: str | None = None
    new_text: str | None = None
    old_knowledge_document_id: int | None = None
    new_knowledge_document_id: int | None = None


class FilingAnalysisContent(BaseModel):
    old_filing: FilingReference
    new_filing: FilingReference
    headline: str
    sections: dict[str, FilingSectionContent]
    evidence: dict[str, dict[str, FilingEvidence]]
    max_importance: Importance


class FilingAnalysisResult(BaseModel):
    analyzed: int = 0
    skipped_existing: int = 0
    skipped_no_pair: int = 0
    failed: dict[int, str] = Field(default_factory=dict)
    llm_calls: int = 0
    signals_created: int = 0
    alerts_created: int = 0
    notes_written: int = 0
    note_failures: dict[int, str] = Field(default_factory=dict)
