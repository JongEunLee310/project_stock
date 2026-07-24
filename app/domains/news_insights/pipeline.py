from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.news_insights.clock import utcnow
from app.domains.news_insights.clustering import (
    ClusteringResult,
    EventClusterer,
    cluster_topics,
)
from app.domains.news_insights.extraction import (
    EventExtractor,
    ExtractionResult,
    extract_events,
)
from app.domains.news_insights.ingestion import (
    SourceDocumentIngestionResult,
    ingest_source_documents,
)
from app.domains.news_insights.interpretation import (
    SKELETON_MODEL_NAME,
    InterpretationResult,
    TopicInterpreter,
    interpret_topics,
)
from app.domains.news_insights.model import (
    AgentRun,
    AgentRunStage,
    TopicCluster,
)
from app.domains.news_insights.types import (
    AgentRunStatus,
    AgentStage,
    LifecycleStatus,
)


ACTIVE_TOPIC_LIFECYCLE_STATUSES = (
    LifecycleStatus.EMERGING.value,
    LifecycleStatus.RISING.value,
    LifecycleStatus.ACTIVE.value,
)


@dataclass(frozen=True)
class PipelineRunResult:
    agent_run_id: int
    ingestion_result: SourceDocumentIngestionResult
    extraction_result: ExtractionResult
    clustering_result: ClusteringResult
    interpretation_result: InterpretationResult


def run_pipeline(
    db: Session,
    extractor: EventExtractor,
    clusterer: EventClusterer,
    interpreter: TopicInterpreter,
) -> PipelineRunResult:
    run = AgentRun(
        started_at=utcnow(),
        finished_at=None,
        status=AgentRunStatus.RUNNING.value,
        processed_documents=0,
        extracted_events=0,
        active_topics=0,
        analysis_version=SKELETON_MODEL_NAME,
    )
    db.add(run)
    db.commit()
    run_id = run.id
    current_stage = AgentStage.COLLECT
    extraction_result = ExtractionResult()

    try:
        ingestion_result = ingest_source_documents(db)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)

        current_stage = AgentStage.EXTRACT
        extraction_result = extract_events(db, extractor)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)

        current_stage = AgentStage.CLUSTER
        clustering_result = cluster_topics(db, clusterer)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)

        current_stage = AgentStage.LINK
        interpretation_result = interpret_topics(db, interpreter)
        _record_stage(db, run_id, current_stage, AgentRunStatus.COMPLETED)
    except Exception:
        db.rollback()
        _record_stage(db, run_id, current_stage, AgentRunStatus.FAILED)
        failed_run = db.get(AgentRun, run_id)
        if failed_run is None:
            raise RuntimeError(f"agent run not found: {run_id}")
        failed_run.status = AgentRunStatus.FAILED.value
        failed_run.finished_at = utcnow()
        failed_run.processed_documents = (
            extraction_result.processed_document_count
        )
        failed_run.extracted_events = extraction_result.created_event_count
        failed_run.active_topics = _count_active_topics(db)
        db.commit()
        raise

    completed_run = db.get(AgentRun, run_id)
    if completed_run is None:
        raise RuntimeError(f"agent run not found: {run_id}")
    completed_run.status = AgentRunStatus.COMPLETED.value
    completed_run.finished_at = utcnow()
    completed_run.processed_documents = (
        extraction_result.processed_document_count
    )
    completed_run.extracted_events = extraction_result.created_event_count
    completed_run.active_topics = _count_active_topics(db)
    db.commit()

    return PipelineRunResult(
        agent_run_id=run_id,
        ingestion_result=ingestion_result,
        extraction_result=extraction_result,
        clustering_result=clustering_result,
        interpretation_result=interpretation_result,
    )


def _record_stage(
    db: Session,
    run_id: int,
    stage: AgentStage,
    status: AgentRunStatus,
) -> None:
    db.add(
        AgentRunStage(
            agent_run_id=run_id,
            stage=stage.value,
            status=status.value,
            delayed=False,
        )
    )
    db.commit()


def _count_active_topics(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count(TopicCluster.id)).where(
                TopicCluster.lifecycle_status.in_(
                    ACTIVE_TOPIC_LIFECYCLE_STATUSES
                )
            )
        )
        or 0
    )
