from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.pagination import PaginationParams
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
    pagination: Annotated[PaginationParams, Depends()],
    db: Session = Depends(get_db),
) -> ApiResponse[list[JobRunResponse]]:
    service = JobRunService(db)
    items = [
        JobRunResponse.model_validate(job_run)
        for job_run in service.list_recent(
            offset=pagination.offset,
            limit=pagination.limit,
        )
    ]
    total = service.count()
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )
