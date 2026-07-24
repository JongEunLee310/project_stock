from dataclasses import dataclass
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.news.normalizer import NewsNormalizer
from app.domains.news_insights.model import SourceDocument
from app.domains.news_insights.types import DocumentType, ProcessingStatus
from app.domains.raw_news.model import RawNewsEvent


@dataclass(frozen=True)
class SourceDocumentIngestionResult:
    inserted_count: int = 0
    skipped_count: int = 0
    duplicate_count: int = 0


def ingest_source_documents(db: Session) -> SourceDocumentIngestionResult:
    raw_events = db.scalars(
        select(RawNewsEvent).order_by(RawNewsEvent.id)
    ).all()
    known_hashes = set(
        db.scalars(select(SourceDocument.content_hash)).all()
    )
    documents: list[SourceDocument] = []
    skipped_count = 0
    duplicate_count = 0

    for raw_event in raw_events:
        document = _map_raw_to_source_document(raw_event)
        if document is None:
            skipped_count += 1
            continue
        if document.content_hash in known_hashes:
            duplicate_count += 1
            continue
        known_hashes.add(document.content_hash)
        documents.append(document)

    db.add_all(documents)
    db.commit()
    return SourceDocumentIngestionResult(
        inserted_count=len(documents),
        skipped_count=skipped_count,
        duplicate_count=duplicate_count,
    )


def _map_raw_to_source_document(
    raw_event: RawNewsEvent,
) -> SourceDocument | None:
    if raw_event.body is None:
        return None

    canonical_url = NewsNormalizer().canonicalize_url(raw_event.url)
    content_hash = hashlib.sha256(
        f"{canonical_url}{raw_event.title}".encode()
    ).hexdigest()
    return SourceDocument(
        document_type=DocumentType.NEWS.value,
        source_name=raw_event.source,
        source_url=raw_event.url,
        external_id=str(raw_event.id),
        title=raw_event.title,
        raw_content=raw_event.body,
        normalized_content=None,
        language="ko",
        published_at=raw_event.published_at or raw_event.collected_at,
        collected_at=raw_event.collected_at,
        content_hash=content_hash,
        source_reliability=0.5,
        processing_status=ProcessingStatus.PENDING.value,
    )
