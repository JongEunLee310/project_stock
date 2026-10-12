from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.adapters.llm.masking import MaskCategory
from app.domains.rag.types import ChunkContentQuality, ChunkSourceType


class ResearchQARequest(BaseModel):
    question: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)
    ]
    lookback_days: int = Field(default=90, ge=1, le=365)
    save_to_obsidian: bool = False


class AnswerPoint(BaseModel):
    text: str
    citations: list[int]


class EvidenceItem(BaseModel):
    id: int
    source_type: ChunkSourceType
    source_id: int
    title: str
    source_name: str
    source_url: str
    published_at: datetime | None
    excerpt: str
    score: float
    content_quality: ChunkContentQuality


class ResearchQAResult(BaseModel):
    answer_points: list[AnswerPoint]
    limitations: str | None
    insufficient_evidence: bool


class ResearchAnswer(ResearchQAResult):
    masked_categories: list[MaskCategory] = Field(default_factory=list)
    evidence: list[EvidenceItem]
    generated_at: datetime
    obsidian_note_path: str | None = None
