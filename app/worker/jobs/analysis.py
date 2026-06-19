import logging

from app.adapters.factory import get_news_adapter
from app.adapters.llm.mock import MockLLMClient
from app.db.session import SessionLocal
from app.domains.analysis.service import WatchlistAnalysisService
from app.domains.jobs.model import JobRun
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
        result = WatchlistAnalysisService(
            db,
            MockLLMClient(
                {
                    "NewsSummaryResult": {
                        "summary": "Mock analysis summary.",
                        "positive_factors": ["Mock positive factor"],
                        "negative_factors": ["Mock negative factor"],
                        "impact_level": "HIGH",
                        "sentiment": "NEUTRAL",
                    },
                    "ThesisConflictResult": {
                        "status": "NEUTRAL",
                        "reason": "Mock conflict analysis is neutral.",
                        "invalidation_triggered": False,
                    },
                }
            ),
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
