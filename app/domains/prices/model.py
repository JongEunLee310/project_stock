from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class StockPriceBar(Base, TimestampMixin):
    __tablename__ = "stock_price_bars"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "market",
            "interval",
            "timestamp",
            name="uq_price_bars_symbol_market_interval_ts",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(20))
    market: Mapped[str] = mapped_column(String(20))
    interval: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    high_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    low_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    close_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    adjusted_close_price: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    volume: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(String(30))
