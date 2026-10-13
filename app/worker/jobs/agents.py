import logging

from rq import Queue

from app.adapters.factory import (
    get_embedder,
    get_llm_gateway,
    get_obsidian_writer,
    get_vector_store,
)
from app.db.session import SessionLocal
from app.domains.agents.daily_research.preparation import prepare_embeddings
from app.domains.agents.daily_research.service import DailyResearchAgent
from app.domains.jobs.service import JobRunService
from app.worker.connection import get_redis_connection
from app.worker.jobs.timeouts import DAILY_RESEARCH_JOB_TIMEOUT

logger = logging.getLogger(__name__)


def enqueue_daily_research_safe(asset_ids: list[int]) -> None:
    try:
        queue = Queue("default", connection=get_redis_connection())
        queue.enqueue(
            run_daily_research_job, asset_ids, job_timeout=DAILY_RESEARCH_JOB_TIMEOUT
        )
    except Exception:
        logger.warning(
            "failed to enqueue daily research: asset_ids=%s", asset_ids, exc_info=True
        )


def run_daily_research_job(asset_ids: list[int] | None = None) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start(
            "daily_research_agent", {"asset_ids": asset_ids}
        )
        job_run_id = job_run.id
        embedder = get_embedder()
        vector_store = get_vector_store(db)
        prepare_embeddings(db, embedder, vector_store)
        result = DailyResearchAgent(
            db,
            embedder,
            vector_store,
            get_llm_gateway(),
            obsidian_writer=get_obsidian_writer(),
        ).run(asset_ids)
        if result.failed or result.note_failures:
            job_run.metadata_ = {
                **(job_run.metadata_ or {}),
                "partial_failures": {
                    "failed": result.failed,
                    "note_failures": result.note_failures,
                },
            }
        job_run_service.succeed(job_run_id)
        logger.info("daily research completed: %s", result.model_dump())
    except Exception as exc:
        db.rollback()
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
