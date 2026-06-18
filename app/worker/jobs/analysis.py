import logging

from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService

logger = logging.getLogger(__name__)


def analyze_watchlist_job(watchlist_id: int) -> None:
    db = SessionLocal()
    job_run_id: int | None = None
    try:
        job_run = JobRunService(db).start(
            "watchlist_analysis", {"watchlist_id": watchlist_id}
        )
        job_run_id = job_run.id
        logger.info(
            "analyze_watchlist_job called: watchlist_id=%s (not implemented)",
            watchlist_id,
        )
        JobRunService(db).succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            JobRunService(db).fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
