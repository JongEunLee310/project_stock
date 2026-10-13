import logging

from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.knowledge.filing_service import FilingCollectionService

logger = logging.getLogger(__name__)


def collect_filings_job(asset_ids: list[int] | None = None) -> None:
    db = SessionLocal()
    runs = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = runs.start("filing_collection", {"asset_ids": asset_ids})
        job_run_id = job_run.id
        result = FilingCollectionService(db).collect(asset_ids)
        job_run.metadata_ = {
            **(job_run.metadata_ or {}),
            "result": result.model_dump(mode="json"),
        }
        if result.failed or result.missing_sections:
            job_run.metadata_ = {
                **job_run.metadata_,
                "partial_failures": {
                    "failed": result.model_dump(mode="json")["failed"],
                    "missing_sections": result.model_dump(mode="json")[
                        "missing_sections"
                    ],
                },
            }
        runs.succeed(job_run_id)
        logger.info("filing collection completed: %s", result.model_dump())
    except Exception as exc:
        db.rollback()
        if job_run_id is not None:
            runs.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
