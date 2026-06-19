import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.reports.model import ResearchReport
from app.domains.reports.schema import ResearchReportCreate


class ResearchReportRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: ResearchReportCreate) -> ResearchReport:
        report = ResearchReport(
            asset_id=data.asset_id,
            thesis_id=data.thesis_id,
            summary=data.summary,
            positive_factors=self._dump_json_array(data.positive_factors),
            negative_factors=self._dump_json_array(data.negative_factors),
            risk_level=data.risk_level,
            thesis_conflict_status=data.thesis_conflict_status,
            conflict_reason=data.conflict_reason,
            news_item_ids=self._dump_json_array(data.news_item_ids),
        )
        self.db.add(report)
        self.db.commit()
        self.db.refresh(report)
        return report

    def get_by_id(self, report_id: int) -> ResearchReport | None:
        return self.db.get(ResearchReport, report_id)

    def list_by_asset(self, asset_id: int) -> list[ResearchReport]:
        stmt = (
            select(ResearchReport)
            .where(ResearchReport.asset_id == asset_id)
            .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def _dump_json_array(self, value: list[str] | list[int] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)
