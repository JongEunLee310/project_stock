import json
from datetime import date
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.domains.reports.model import ResearchReport
from app.domains.reports.schema import ResearchReportCreate
from app.domains.reports.types import ReportType


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

    def upsert_daily_brief(
        self,
        asset_id: int,
        brief_date: date,
        summary: str,
        risk_level: str | None,
        content: dict[str, Any],
    ) -> ResearchReport:
        insert = (
            sqlite_insert if self.db.get_bind().dialect.name == "sqlite" else pg_insert
        )
        stmt = insert(ResearchReport).values(
            asset_id=asset_id,
            report_type=ReportType.DAILY_BRIEF.value,
            brief_date=brief_date,
            summary=summary,
            risk_level=risk_level,
            content=content,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[ResearchReport.asset_id, ResearchReport.brief_date],
            index_where=text("report_type = 'DAILY_BRIEF'"),
            set_={
                "summary": stmt.excluded.summary,
                "risk_level": stmt.excluded.risk_level,
                "content": stmt.excluded.content,
                "updated_at": func.now(),
            },
        )
        self.db.flush()
        return self.db.scalars(
            stmt.returning(ResearchReport),
            execution_options={"populate_existing": True},
        ).one()

    def get_latest_daily_brief(self, asset_id: int) -> ResearchReport | None:
        stmt = (
            select(ResearchReport)
            .where(
                ResearchReport.asset_id == asset_id,
                ResearchReport.report_type == ReportType.DAILY_BRIEF.value,
            )
            .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def list_by_asset(
        self,
        asset_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[ResearchReport]:
        stmt = (
            select(ResearchReport)
            .where(ResearchReport.asset_id == asset_id)
            .order_by(ResearchReport.created_at.desc(), ResearchReport.id.desc())
        )
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_asset(self, asset_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(ResearchReport)
            .where(ResearchReport.asset_id == asset_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def _dump_json_array(self, value: list[str] | list[int] | None) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)
