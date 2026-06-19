from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.domains.reports.schema import ResearchReportCreate, ResearchReportResponse
from app.domains.reports.service import ResearchReportService
from app.domains.users.model import User

router = APIRouter()


@router.post("", response_model=ResearchReportResponse, status_code=201)
def create_report(
    data: ResearchReportCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchReportResponse:
    return ResearchReportResponse.model_validate(
        ResearchReportService(db).create_report(data)
    )


@router.get("", response_model=list[ResearchReportResponse])
def list_reports(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[ResearchReportResponse]:
    return [
        ResearchReportResponse.model_validate(report)
        for report in ResearchReportService(db).list_reports(asset_id)
    ]


@router.get("/{report_id}", response_model=ResearchReportResponse)
def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResearchReportResponse:
    return ResearchReportResponse.model_validate(
        ResearchReportService(db).get_report(report_id)
    )
