from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class EarningsReport(Base, TimestampMixin):
    __tablename__ = "earnings_reports"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "market", "period",
            name="uq_earnings_reports_symbol_market_period",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(10))
    period_end: Mapped[date] = mapped_column(Date)
    revenue: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    operating_income: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    eps: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    eps_estimate: Mapped[Decimal | None] = mapped_column(
        Numeric(20, 4), nullable=True
    )
    source: Mapped[str] = mapped_column(String(30))
