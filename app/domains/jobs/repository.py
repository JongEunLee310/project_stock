from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.jobs.model import JobRun
from app.domains.jobs.schema import JobRunCreate


class JobRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        data: JobRunCreate,
        status: str = "pending",
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_message: str | None = None,
    ) -> JobRun:
        job_run = JobRun(
            job_type=data.job_type,
            status=status,
            started_at=started_at,
            finished_at=finished_at,
            error_message=error_message,
            metadata_=data.metadata,
        )
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

    def list_recent(self, offset: int = 0, limit: int | None = None) -> list[JobRun]:
        stmt = (
            select(JobRun)
            .order_by(JobRun.created_at.desc(), JobRun.id.desc())
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_all(self) -> int:
        stmt = select(func.count()).select_from(JobRun)
        return int(self.db.scalar(stmt) or 0)
