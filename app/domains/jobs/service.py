from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.domains.jobs.model import JobRun
from app.domains.jobs.repository import JobRunRepository
from app.domains.jobs.schema import JobRunCreate


class JobRunService:
    def __init__(self, db: Session) -> None:
        self.repo = JobRunRepository(db)

    def start(self, job_type: str, metadata: dict[str, Any] | None = None) -> JobRun:
        return self.repo.create(
            JobRunCreate(job_type=job_type, metadata=metadata),
            status="running",
            started_at=datetime.now(timezone.utc),
        )

    def succeed(self, job_run_id: int) -> JobRun:
        return self.repo.update_status(
            job_run_id,
            "success",
            finished_at=datetime.now(timezone.utc),
        )

    def fail(self, job_run_id: int, error_message: str) -> JobRun:
        return self.repo.update_status(
            job_run_id,
            "failed",
            finished_at=datetime.now(timezone.utc),
            error_message=error_message,
        )

    def list_recent(self, offset: int = 0, limit: int | None = None) -> list[JobRun]:
        return self.repo.list_recent(offset=offset, limit=limit)

    def count(self) -> int:
        return self.repo.count_all()
