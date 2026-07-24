from abc import ABC, abstractmethod
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.domains.news_insights.briefing import (
    validate_evidence_event_ids,
)
from app.domains.news_insights.clock import utcnow
from app.domains.news_insights.model import (
    ExplanationFactor,
    ExtractedEvent,
    TopicCluster,
    TopicExplanation,
    TopicInsight,
)
from app.domains.news_insights.types import EventType


SKELETON_ANALYSIS_VERSION = "v0-skeleton"
SKELETON_MODEL_NAME = "rule-based-skeleton"
SKELETON_SCORE = 0.5
SKELETON_VERSION = 1


@dataclass(frozen=True)
class TopicInterpretationDraft:
    version: int
    executive_summary: str
    why_it_matters: str
    key_evidence_event_ids: tuple[int, ...]
    risk_points: tuple[str, ...]
    counter_arguments: tuple[str, ...]
    impact_score: float
    confidence_score: float
    model_name: str
    prompt_version: str
    data_coverage: float
    explanation_confidence: float
    missing_data: tuple[str, ...]
    limitations: tuple[str, ...]
    already_priced_in: bool
    already_priced_in_note: str | None
    analysis_version: str
    factors: tuple[()]


class TopicInterpreter(ABC):
    @abstractmethod
    def interpret(
        self,
        topic: TopicCluster,
        events: list[ExtractedEvent],
    ) -> TopicInterpretationDraft | None:
        """Create an interpretation draft from evidence-backed events."""


class RuleBasedTopicInterpreter(TopicInterpreter):
    def interpret(
        self,
        topic: TopicCluster,
        events: list[ExtractedEvent],
    ) -> TopicInterpretationDraft | None:
        if not events:
            return None

        return TopicInterpretationDraft(
            version=SKELETON_VERSION,
            executive_summary=(
                f"{topic.title} 토픽의 집계 언급 수는 "
                f"{topic.mention_count}건입니다."
            ),
            why_it_matters=(
                f"{topic.title} 토픽의 집계 영향도는 "
                f"{topic.impact_score:.2f}입니다."
            ),
            key_evidence_event_ids=tuple(event.id for event in events),
            risk_points=(
                f"{topic.title} 토픽의 위험 요인은 "
                "골격 해석기에서 산출하지 않습니다.",
            ),
            counter_arguments=(
                f"{topic.title} 토픽의 반론은 "
                "골격 해석기에서 산출하지 않습니다.",
            ),
            impact_score=topic.impact_score,
            confidence_score=topic.confidence_score,
            model_name=SKELETON_MODEL_NAME,
            prompt_version=SKELETON_ANALYSIS_VERSION,
            data_coverage=SKELETON_SCORE,
            explanation_confidence=SKELETON_SCORE,
            missing_data=("실 해석기 미도입",),
            limitations=("근거 연결이 event_type 기준 재조회",),
            already_priced_in=False,
            already_priced_in_note=None,
            analysis_version=SKELETON_ANALYSIS_VERSION,
            factors=(),
        )


@dataclass(frozen=True)
class InterpretationResult:
    created_insight_count: int = 0
    updated_insight_count: int = 0
    created_explanation_count: int = 0
    updated_explanation_count: int = 0
    created_factor_count: int = 0
    skipped_topic_count: int = 0


def interpret_topics(
    db: Session,
    interpreter: TopicInterpreter,
) -> InterpretationResult:
    topics = list(
        db.scalars(select(TopicCluster).order_by(TopicCluster.id)).all()
    )
    if not topics:
        return InterpretationResult()

    interpreted_at = utcnow()
    created_insight_count = 0
    updated_insight_count = 0
    created_explanation_count = 0
    updated_explanation_count = 0
    skipped_topic_count = 0

    for topic in topics:
        events = _evidence_events_for_topic(db, topic)
        draft = interpreter.interpret(topic, events)
        if draft is None:
            skipped_topic_count += 1
            continue

        evidence_event_ids = validate_evidence_event_ids(
            draft.key_evidence_event_ids,
            {event.id for event in events},
        )
        if not evidence_event_ids:
            skipped_topic_count += 1
            continue

        insight = db.scalar(
            select(TopicInsight).where(
                TopicInsight.topic_id == topic.id,
                TopicInsight.version == SKELETON_VERSION,
            )
        )
        if insight is None:
            insight = TopicInsight(
                topic_id=topic.id,
                version=SKELETON_VERSION,
                executive_summary=draft.executive_summary,
                why_it_matters=draft.why_it_matters,
                key_evidence=[
                    {"event_id": event_id}
                    for event_id in evidence_event_ids
                ],
                risk_points=list(draft.risk_points),
                counter_arguments=list(draft.counter_arguments),
                impact_score=draft.impact_score,
                confidence_score=draft.confidence_score,
                model_name=draft.model_name,
                prompt_version=draft.prompt_version,
            )
            db.add(insight)
            created_insight_count += 1
        else:
            insight.executive_summary = draft.executive_summary
            insight.why_it_matters = draft.why_it_matters
            insight.key_evidence = [
                {"event_id": event_id}
                for event_id in evidence_event_ids
            ]
            insight.risk_points = list(draft.risk_points)
            insight.counter_arguments = list(draft.counter_arguments)
            insight.impact_score = draft.impact_score
            insight.confidence_score = draft.confidence_score
            insight.model_name = draft.model_name
            insight.prompt_version = draft.prompt_version
            updated_insight_count += 1

        explanation = db.scalar(
            select(TopicExplanation).where(
                TopicExplanation.topic_id == topic.id
            )
        )
        if explanation is None:
            explanation = TopicExplanation(
                topic_id=topic.id,
                analysis_version=draft.analysis_version,
                data_coverage=draft.data_coverage,
                confidence=draft.explanation_confidence,
                missing_data=list(draft.missing_data),
                limitations=list(draft.limitations),
                already_priced_in=draft.already_priced_in,
                already_priced_in_note=draft.already_priced_in_note,
                last_updated=interpreted_at,
            )
            db.add(explanation)
            db.flush()
            created_explanation_count += 1
        else:
            explanation.analysis_version = draft.analysis_version
            explanation.data_coverage = draft.data_coverage
            explanation.confidence = draft.explanation_confidence
            explanation.missing_data = list(draft.missing_data)
            explanation.limitations = list(draft.limitations)
            explanation.already_priced_in = draft.already_priced_in
            explanation.already_priced_in_note = (
                draft.already_priced_in_note
            )
            explanation.last_updated = interpreted_at
            updated_explanation_count += 1

        db.execute(
            delete(ExplanationFactor).where(
                ExplanationFactor.topic_explanation_id == explanation.id
            )
        )
    db.commit()
    return InterpretationResult(
        created_insight_count=created_insight_count,
        updated_insight_count=updated_insight_count,
        created_explanation_count=created_explanation_count,
        updated_explanation_count=updated_explanation_count,
        created_factor_count=0,
        skipped_topic_count=skipped_topic_count,
    )


def _evidence_events_for_topic(
    db: Session,
    topic: TopicCluster,
) -> list[ExtractedEvent]:
    try:
        event_type = EventType(topic.slug.replace("-", "_").upper())
    except ValueError:
        return []
    return list(
        db.scalars(
            select(ExtractedEvent)
            .where(ExtractedEvent.event_type == event_type.value)
            .order_by(ExtractedEvent.id)
        ).all()
    )
