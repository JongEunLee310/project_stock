from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, paginated
from app.db.session import get_db
from app.domains.jobs.schema import JobRunResponse
from app.domains.jobs.service import JobRunService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[JobRunResponse]],
    summary="List job runs",
    description="Return paginated background job execution records.",
)
def list_job_runs(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> ApiResponse[list[JobRunResponse]]:
    service = JobRunService(db)
    items = [
        JobRunResponse.model_validate(job_run)
        for job_run in service.list_recent(offset=(page - 1) * size, limit=size)
    ]
    total = service.count()
    return paginated(items, page=page, size=size, total=total)
