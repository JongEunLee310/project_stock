from pydantic import BaseModel, Field


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
