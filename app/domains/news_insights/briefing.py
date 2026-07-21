from collections.abc import Iterable, Set
from dataclasses import dataclass
from datetime import datetime

from app.domains.news_insights.schema import (
    BriefingHighlight,
    BriefingResponse,
)


@dataclass(frozen=True)
class BriefingCandidate:
    text: str
    topic_id: int
    evidence_event_ids: tuple[int, ...]


def validate_evidence_event_ids(
    evidence_event_ids: Iterable[int],
    existing_event_ids: Set[int],
) -> list[int]:
    """Keep unique evidence references that resolve to an existing event."""
    validated: list[int] = []
    for event_id in evidence_event_ids:
        if event_id in existing_event_ids and event_id not in validated:
            validated.append(event_id)
    return validated


def build_briefing(
    candidates: Iterable[BriefingCandidate],
    *,
    existing_event_ids: Set[int],
    generated_at: datetime,
) -> BriefingResponse:
    highlights: list[BriefingHighlight] = []
    for candidate in candidates:
        evidence_event_ids = validate_evidence_event_ids(
            candidate.evidence_event_ids,
            existing_event_ids,
        )
        if not evidence_event_ids:
            continue
        highlights.append(
            BriefingHighlight(
                text=candidate.text,
                topic_id=candidate.topic_id,
                evidence_count=len(evidence_event_ids),
                evidence_event_ids=evidence_event_ids,
            )
        )
    summary = (
        "주요 뉴스 이벤트와 연결된 근거를 요약했습니다."
        if highlights
        else "현재 브리핑에 포함할 근거 이벤트가 없습니다."
    )
    return BriefingResponse(
        summary=summary,
        highlights=highlights,
        generated_at=generated_at,
    )
