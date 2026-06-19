from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class Portfolio(Base, TimestampMixin):
    __tablename__ = "portfolios"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255))


class Position(Base, TimestampMixin):
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint(
            "portfolio_id",
            "asset_id",
            name="uq_positions_portfolio_asset",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id"))
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    avg_buy_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
