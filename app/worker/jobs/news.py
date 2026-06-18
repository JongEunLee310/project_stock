from app.adapters.news.mock import MockNewsAdapter
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.raw_news.service import RawNewsService


def collect_news_job(symbols: list[str]) -> None:
    db = SessionLocal()
    job_run_id: int | None = None
    try:
        job_run = JobRunService(db).start("news_collection", {"symbols": symbols})
        job_run_id = job_run.id
        RawNewsService(db).collect_and_save(MockNewsAdapter(), symbols)
        JobRunService(db).succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            JobRunService(db).fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
