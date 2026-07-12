from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import EarningsReportResult
from app.adapters.market.yfinance import period_from_end
from app.domains.earnings.model import EarningsReport


class EarningsRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self, symbol: str, market: str, result: EarningsReportResult
    ) -> EarningsReport:
        period = period_from_end(result.period_end)
        report = self.db.scalars(
            select(EarningsReport).where(
                EarningsReport.symbol == symbol,
                EarningsReport.market == market,
                EarningsReport.period == period,
            )
        ).first()
        values = {
            "period_end": result.period_end,
            "revenue": result.revenue,
            "operating_income": result.operating_income,
            "eps": result.eps,
            "eps_estimate": result.eps_estimate,
            "source": result.source,
        }
        if report is None:
            report = EarningsReport(
                symbol=symbol, market=market, period=period, **values
            )
            self.db.add(report)
        else:
            for field, value in values.items():
                setattr(report, field, value)
        self.db.commit()
        self.db.refresh(report)
        return report

    def get_recent(
        self, symbol: str, market: str, limit: int
    ) -> list[EarningsReport]:
        stmt = (
            select(EarningsReport)
            .where(
                EarningsReport.symbol == symbol,
                EarningsReport.market == market,
            )
            .order_by(EarningsReport.period_end.desc(), EarningsReport.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt))

    def get_coverage(self, symbol: str, market: str) -> tuple[int, datetime | None]:
        stmt = select(
            func.count(EarningsReport.id), func.max(EarningsReport.updated_at)
        ).where(
            EarningsReport.symbol == symbol,
            EarningsReport.market == market,
        )
        item_count, last_updated_at = self.db.execute(stmt).one()
        return item_count, last_updated_at
