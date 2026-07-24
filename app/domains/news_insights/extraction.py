from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
import hashlib

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.news_insights.clock import utcnow
from app.domains.news_insights.model import (
    EventEvidence,
    ExtractedEvent,
    SourceDocument,
)
from app.domains.news_insights.types import (
    EventStatus,
    EventType,
    EvidenceRole,
    ProcessingStatus,
    SentimentDirection,
)


NEUTRAL_SCORE = 0.5


@dataclass(frozen=True)
class EvidenceDraft:
    evidence_role: EvidenceRole
    relevance_score: float
    extracted_quote: str | None


@dataclass(frozen=True)
class ExtractedEventDraft:
    event_type: EventType
    title: str
    summary: str
    importance_score: float
    sentiment_direction: SentimentDirection
    sentiment_score: float
    confidence_score: float
    occurred_at: datetime | None
    detected_at: datetime
    primary_symbol: str | None
    sector_code: str | None
    event_fingerprint: str
    status: EventStatus
    evidence: tuple[EvidenceDraft, ...]


class EventExtractor(ABC):
    @abstractmethod
    def extract(self, document: SourceDocument) -> list[ExtractedEventDraft]:
        """Extract zero or more event drafts from one source document."""


class RuleBasedEventExtractor(EventExtractor):
    _EVENT_KEYWORDS: tuple[tuple[EventType, tuple[str, ...]], ...] = (
        (
            EventType.EARNINGS_GUIDANCE,
            ("실적 전망", "가이던스", "earnings guidance"),
        ),
        (
            EventType.BUYBACK,
            ("자사주 매입", "자사주 취득", "share buyback"),
        ),
        (
            EventType.REGULATION,
            ("규제", "regulation"),
        ),
        (
            EventType.SUPPLY_CONTRACT,
            ("공급계약", "supply contract"),
        ),
        (
            EventType.MANAGEMENT_CHANGE,
            ("대표이사 변경", "경영진 교체", "management change"),
        ),
    )
    _POSITIVE_KEYWORDS = ("증가", "성장", "상향")
    _NEGATIVE_KEYWORDS = ("감소", "하락", "하향")

    def extract(self, document: SourceDocument) -> list[ExtractedEventDraft]:
        source_text = f"{document.title}\n{document.raw_content}".casefold()
        event_type = self._detect_event_type(source_text)
        if event_type is None:
            return []

        primary_symbol: str | None = None
        fingerprint = hashlib.sha256(
            (
                f"{event_type.value}|{primary_symbol or ''}|"
                f"{document.content_hash}"
            ).encode()
        ).hexdigest()
        return [
            ExtractedEventDraft(
                event_type=event_type,
                title=document.title,
                summary=document.raw_content,
                importance_score=NEUTRAL_SCORE,
                sentiment_direction=self._detect_sentiment(source_text),
                sentiment_score=NEUTRAL_SCORE,
                confidence_score=NEUTRAL_SCORE,
                occurred_at=None,
                detected_at=utcnow(),
                primary_symbol=primary_symbol,
                sector_code=None,
                event_fingerprint=fingerprint,
                status=EventStatus.ACTIVE,
                evidence=(
                    EvidenceDraft(
                        evidence_role=EvidenceRole.PRIMARY,
                        relevance_score=NEUTRAL_SCORE,
                        extracted_quote=None,
                    ),
                ),
            )
        ]

    def _detect_event_type(self, source_text: str) -> EventType | None:
        for event_type, keywords in self._EVENT_KEYWORDS:
            if any(keyword in source_text for keyword in keywords):
                return event_type
        return None

    def _detect_sentiment(self, source_text: str) -> SentimentDirection:
        has_positive = any(
            keyword in source_text for keyword in self._POSITIVE_KEYWORDS
        )
        has_negative = any(
            keyword in source_text for keyword in self._NEGATIVE_KEYWORDS
        )
        if has_positive and has_negative:
            return SentimentDirection.MIXED
        if has_positive:
            return SentimentDirection.POSITIVE
        if has_negative:
            return SentimentDirection.NEGATIVE
        return SentimentDirection.NEUTRAL


@dataclass(frozen=True)
class ExtractionResult:
    processed_document_count: int = 0
    created_event_count: int = 0
    created_evidence_count: int = 0
    idempotent_skip_count: int = 0
    failed_document_count: int = 0


def extract_events(
    db: Session,
    extractor: EventExtractor,
) -> ExtractionResult:
    pending_document_ids = list(
        db.scalars(
            select(SourceDocument.id)
            .where(
                SourceDocument.processing_status
                == ProcessingStatus.PENDING.value
            )
            .order_by(SourceDocument.id)
        ).all()
    )
    known_fingerprints = set(
        db.scalars(select(ExtractedEvent.event_fingerprint)).all()
    )
    created_event_count = 0
    created_evidence_count = 0
    idempotent_skip_count = 0
    failed_document_count = 0

    for document_id in pending_document_ids:
        try:
            document = db.get(SourceDocument, document_id)
            if document is None:
                raise LookupError(f"source document not found: {document_id}")
            drafts = extractor.extract(document)
            _validate_evidence(drafts)
            local_fingerprints: set[str] = set()
            local_event_count = 0
            local_evidence_count = 0
            local_skip_count = 0

            for draft in drafts:
                if (
                    draft.event_fingerprint in known_fingerprints
                    or draft.event_fingerprint in local_fingerprints
                ):
                    local_skip_count += 1
                    continue
                event = _event_from_draft(draft)
                db.add(event)
                db.flush()
                evidence = [
                    EventEvidence(
                        event_id=event.id,
                        document_id=document.id,
                        relevance_score=item.relevance_score,
                        evidence_role=item.evidence_role.value,
                        extracted_quote=item.extracted_quote,
                    )
                    for item in draft.evidence
                ]
                db.add_all(evidence)
                local_fingerprints.add(draft.event_fingerprint)
                local_event_count += 1
                local_evidence_count += len(evidence)

            document.processing_status = ProcessingStatus.EXTRACTED.value
            db.commit()
            known_fingerprints.update(local_fingerprints)
            created_event_count += local_event_count
            created_evidence_count += local_evidence_count
            idempotent_skip_count += local_skip_count
        except Exception:
            db.rollback()
            failed_document = db.get(SourceDocument, document_id)
            if failed_document is None:
                raise
            failed_document.processing_status = ProcessingStatus.FAILED.value
            db.commit()
            failed_document_count += 1

    return ExtractionResult(
        processed_document_count=len(pending_document_ids),
        created_event_count=created_event_count,
        created_evidence_count=created_evidence_count,
        idempotent_skip_count=idempotent_skip_count,
        failed_document_count=failed_document_count,
    )


def _validate_evidence(drafts: list[ExtractedEventDraft]) -> None:
    for draft in drafts:
        if not draft.evidence:
            raise ValueError("every extracted event requires evidence")
        if not any(
            item.evidence_role is EvidenceRole.PRIMARY
            for item in draft.evidence
        ):
            raise ValueError("every extracted event requires PRIMARY evidence")


def _event_from_draft(draft: ExtractedEventDraft) -> ExtractedEvent:
    return ExtractedEvent(
        event_type=draft.event_type.value,
        title=draft.title,
        summary=draft.summary,
        importance_score=draft.importance_score,
        sentiment_direction=draft.sentiment_direction.value,
        sentiment_score=draft.sentiment_score,
        confidence_score=draft.confidence_score,
        occurred_at=draft.occurred_at,
        detected_at=draft.detected_at,
        primary_symbol=draft.primary_symbol,
        sector_code=draft.sector_code,
        event_fingerprint=draft.event_fingerprint,
        status=draft.status.value,
    )
