import logging

from rq import Queue
from sqlalchemy import select

from app.adapters.factory import get_llm_gateway, get_news_adapter
from app.db.session import SessionLocal
from app.domains.analysis.service import WatchlistAnalysisService
from app.domains.jobs.model import JobRun
from app.domains.jobs.service import JobRunService
from app.domains.watchlists.model import Watchlist
from app.worker.connection import get_redis_connection

logger = logging.getLogger(__name__)


def enqueue_watchlist_analysis_safe(watchlist_id: int) -> None:
    try:
        queue = Queue("default", connection=get_redis_connection())
        queue.enqueue(analyze_watchlist_job, watchlist_id)
    except Exception:
        logger.warning(
            "failed to enqueue watchlist analysis: watchlist_id=%s",
            watchlist_id,
            exc_info=True,
        )


def analyze_watchlist_job(watchlist_id: int) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start(
            "watchlist_analysis", {"watchlist_id": watchlist_id}
        )
        job_run_id = job_run.id
        result = WatchlistAnalysisService(
            db,
            get_llm_gateway(),
            get_news_adapter(),
        ).run(watchlist_id)
        if result.failures:
            _record_partial_failures(job_run, result.failures)
        logger.info(
            "analyze_watchlist_job completed: watchlist_id=%s result=%s",
            watchlist_id,
            result.model_dump(),
        )
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, _error_message(exc))
        raise
    finally:
        db.close()


def analyze_all_watchlists_job() -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        watchlist_ids = list(db.scalars(select(Watchlist.id).order_by(Watchlist.id)))
        job_run = job_run_service.start(
            "all_watchlists_analysis",
            {"watchlist_ids": watchlist_ids},
        )
        job_run_id = job_run.id
        failures: list[dict[str, object]] = []
        service = WatchlistAnalysisService(
            db,
            get_llm_gateway(),
            get_news_adapter(),
        )
        for watchlist_id in watchlist_ids:
            try:
                result = service.run(watchlist_id)
                failures.extend(
                    {"watchlist_id": watchlist_id, **failure}
                    for failure in result.failures
                )
            except Exception as exc:
                db.rollback()
                failures.append(
                    {
                        "watchlist_id": watchlist_id,
                        "error": _error_message(exc),
                    }
                )
                logger.warning(
                    "watchlist analysis failed: watchlist_id=%s",
                    watchlist_id,
                    exc_info=True,
                )
        if failures:
            _record_partial_failures(job_run, failures)
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, _error_message(exc))
        raise
    finally:
        db.close()


def _record_partial_failures(
    job_run: JobRun,
    failures: list[dict[str, object]],
) -> None:
    metadata = dict(job_run.metadata_ or {})
    metadata["partial_failures"] = failures
    job_run.metadata_ = metadata


def _error_message(exc: Exception) -> str:
    detail = getattr(exc, "detail", None)
    if isinstance(detail, str) and detail:
        return detail
    return str(exc)
