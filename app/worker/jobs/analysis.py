import logging

from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService

logger = logging.getLogger(__name__)


def analyze_watchlist_job(watchlist_id: int) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start(
            "watchlist_analysis", {"watchlist_id": watchlist_id}
        )
        job_run_id = job_run.id
        logger.info(
            "analyze_watchlist_job called: watchlist_id=%s (not implemented)",
            watchlist_id,
        )
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
