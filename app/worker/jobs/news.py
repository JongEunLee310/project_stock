from app.adapters.news.mock import MockNewsAdapter
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.raw_news.service import RawNewsService


def collect_news_job(symbols: list[str]) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start("news_collection", {"symbols": symbols})
        job_run_id = job_run.id
        RawNewsService(db).collect_and_save(MockNewsAdapter(), symbols)
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
