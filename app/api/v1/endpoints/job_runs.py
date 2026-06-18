from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.jobs.schema import JobRunResponse
from app.domains.jobs.service import JobRunService

router = APIRouter()


@router.get("", response_model=list[JobRunResponse])
def list_job_runs(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    db: Session = Depends(get_db),
) -> list[JobRunResponse]:
    return [
        JobRunResponse.model_validate(job_run)
        for job_run in JobRunService(db).list_recent(limit=limit)
    ]
