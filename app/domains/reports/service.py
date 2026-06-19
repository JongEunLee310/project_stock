from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.reports.model import ResearchReport
from app.domains.reports.repository import ResearchReportRepository
from app.domains.reports.schema import ResearchReportCreate


class ResearchReportService:
    def __init__(self, db: Session) -> None:
        self.repo = ResearchReportRepository(db)

    def create_report(self, data: ResearchReportCreate) -> ResearchReport:
        return self.repo.create(data)

    def get_report(self, report_id: int) -> ResearchReport:
        report = self.repo.get_by_id(report_id)
        if report is None:
            raise AppException(status_code=404, detail="리포트를 찾을 수 없습니다.")
        return report

    def list_reports(self, asset_id: int) -> list[ResearchReport]:
        return self.repo.list_by_asset(asset_id)
