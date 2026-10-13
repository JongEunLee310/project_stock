from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.domains.knowledge.types import KnowledgeKind


class KnowledgeDocumentCreate(BaseModel):
    kind: KnowledgeKind
    title: str = Field(max_length=500)
    content: str
    asset_id: int | None = None
    source_name: str = Field(max_length=100)
    source_url: str = Field(max_length=1000)
    license_note: str | None = Field(default=None, max_length=255)
    effective_date: date | None = None
    external_id: str = Field(max_length=200)
    content_hash: str = Field(max_length=64)
    metadata_: dict[str, Any] = Field(default_factory=dict)
