from datetime import UTC, date, datetime, time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.market.base import PriceBarResult
from app.domains.prices.model import StockPriceBar


class PriceBarRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert_many(self, bars: list[PriceBarResult]) -> None:
        self.upsert_bars(bars)

    def upsert_bars(self, bars: list[PriceBarResult]) -> int:
        for bar in bars:
            existing = self.get_by_unique_key(
                symbol=bar.symbol,
                market=bar.market,
                interval=bar.interval,
                timestamp=bar.timestamp,
            )
            if existing is None:
                self.db.add(
                    StockPriceBar(
                        symbol=bar.symbol,
                        market=bar.market,
                        interval=bar.interval,
                        timestamp=bar.timestamp,
                        open_price=bar.open_price,
                        high_price=bar.high_price,
                        low_price=bar.low_price,
                        close_price=bar.close_price,
                        adjusted_close_price=bar.adjusted_close_price,
                        volume=bar.volume,
                        currency=bar.currency,
                        source=bar.source,
                    )
                )
                continue
            existing.open_price = bar.open_price
            existing.high_price = bar.high_price
            existing.low_price = bar.low_price
            existing.close_price = bar.close_price
            existing.adjusted_close_price = bar.adjusted_close_price
            existing.volume = bar.volume
            existing.currency = bar.currency
            existing.source = bar.source
        self.db.commit()
        return len(bars)

    def get_by_unique_key(
        self,
        symbol: str,
        market: str,
        interval: str,
        timestamp: datetime,
    ) -> StockPriceBar | None:
        stmt = select(StockPriceBar).where(
            StockPriceBar.symbol == symbol,
            StockPriceBar.market == market,
            StockPriceBar.interval == interval,
            StockPriceBar.timestamp == timestamp,
        )
        return self.db.scalars(stmt).first()

    def list_recent(
        self,
        symbol: str,
        market: str,
        interval: str,
        limit: int,
    ) -> list[StockPriceBar]:
        stmt = (
            select(StockPriceBar)
            .where(
                StockPriceBar.symbol == symbol,
                StockPriceBar.market == market,
                StockPriceBar.interval == interval,
            )
            .order_by(StockPriceBar.timestamp.desc())
            .limit(limit)
        )
        return list(reversed(self.db.scalars(stmt).all()))

    def get_daily_closes(
        self,
        symbol: str,
        market: str,
        start: date | None,
    ) -> list[tuple[date, Decimal]]:
        stmt = (
            select(StockPriceBar.timestamp, StockPriceBar.close_price)
            .where(
                StockPriceBar.symbol == symbol,
                StockPriceBar.market == market,
                StockPriceBar.interval == "1d",
            )
            .order_by(StockPriceBar.timestamp)
        )
        if start is not None:
            start_timestamp = datetime.combine(start, time.min, tzinfo=UTC)
            stmt = stmt.where(StockPriceBar.timestamp >= start_timestamp)
        return [
            (timestamp.date(), close_price)
            for timestamp, close_price in self.db.execute(stmt).all()
        ]
