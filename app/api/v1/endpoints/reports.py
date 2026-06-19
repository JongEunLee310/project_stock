from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.reports.schema import ResearchReportCreate, ResearchReportResponse
from app.domains.reports.service import ResearchReportService
from app.domains.users.model import User

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[ResearchReportResponse],
    status_code=201,
    summary="Create research report",
    description="Create a research report for an asset, optionally linked to a thesis and source news items.",
)
def create_report(
    data: ResearchReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ResearchReportResponse]:
    return success(
        ResearchReportResponse.model_validate(
            ResearchReportService(db).create_report(data)
        )
    )


@router.get(
    "",
    response_model=ApiResponse[list[ResearchReportResponse]],
    summary="List research reports",
    description="Return paginated research reports for an asset.",
)
def list_reports(
    asset_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[ResearchReportResponse]]:
    service = ResearchReportService(db)
    items = [
        ResearchReportResponse.model_validate(report)
        for report in service.list_reports(
            asset_id,
            offset=(page - 1) * size,
            limit=size,
        )
    ]
    total = service.count_reports(asset_id)
    return paginated(items, page=page, size=size, total=total)


@router.get(
    "/{report_id}",
    response_model=ApiResponse[ResearchReportResponse],
    summary="Get research report",
    description="Return a single research report by id.",
)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ResearchReportResponse]:
    return success(
        ResearchReportResponse.model_validate(
            ResearchReportService(db).get_report(report_id)
        )
    )
