from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.jobs.model import JobRun


class JobRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, job_type: str, metadata: dict[str, Any] | None) -> JobRun:
        job_run = JobRun(job_type=job_type, status="pending", metadata_=metadata)
        self.db.add(job_run)
        self.db.commit()
        self.db.refresh(job_run)
        return job_run

    def update_status(
        self,
        id: int,
        status: str,
        **kwargs: datetime | str | None,
    ) -> JobRun:
        job_run = self.db.get(JobRun, id)
        if job_run is None:
            raise ValueError("job run not found")
        job_run.status = status
        for field, value in kwargs.items():
            setattr(job_run, field, value)
        self.db.commit()
        self.db.refresh(job_run)
        return job_run

    def list_recent(self, limit: int) -> list[JobRun]:
        stmt = (
            select(JobRun)
            .order_by(JobRun.created_at.desc(), JobRun.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())
