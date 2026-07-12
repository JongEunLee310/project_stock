from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ValuationSnapshot(Base, TimestampMixin):
    __tablename__ = "valuation_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "symbol", "market", "as_of",
            name="uq_valuation_snapshots_symbol_market_as_of",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(20))
    as_of: Mapped[date] = mapped_column(Date)
    per: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    forward_per: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    psr: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    pbr: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    ev_ebitda: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    peg: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    fcf_yield: Mapped[Decimal | None] = mapped_column(Numeric(20, 4), nullable=True)
    source: Mapped[str] = mapped_column(String(30))
