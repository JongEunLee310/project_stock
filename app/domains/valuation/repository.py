from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import ValuationResult
from app.domains.valuation.model import ValuationSnapshot


class ValuationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def upsert(
        self, symbol: str, market: str, result: ValuationResult
    ) -> ValuationSnapshot:
        snapshot = self.db.scalars(
            select(ValuationSnapshot).where(
                ValuationSnapshot.symbol == symbol,
                ValuationSnapshot.market == market,
                ValuationSnapshot.as_of == result.as_of,
            )
        ).first()
        values = {
            "per": result.per,
            "forward_per": result.forward_per,
            "psr": result.psr,
            "pbr": result.pbr,
            "ev_ebitda": result.ev_ebitda,
            "peg": result.peg,
            "fcf_yield": result.fcf_yield,
            "source": result.source,
        }
        if snapshot is None:
            snapshot = ValuationSnapshot(
                symbol=symbol, market=market, as_of=result.as_of, **values
            )
            self.db.add(snapshot)
        else:
            for field, value in values.items():
                setattr(snapshot, field, value)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def get_latest(self, symbol: str, market: str) -> ValuationSnapshot | None:
        stmt = (
            select(ValuationSnapshot)
            .where(
                ValuationSnapshot.symbol == symbol,
                ValuationSnapshot.market == market,
            )
            .order_by(ValuationSnapshot.as_of.desc(), ValuationSnapshot.id.desc())
            .limit(1)
        )
        return self.db.scalars(stmt).first()

    def get_coverage(self, symbol: str, market: str) -> tuple[int, datetime | None]:
        stmt = select(
            func.count(ValuationSnapshot.id),
            func.max(ValuationSnapshot.updated_at),
        ).where(
            ValuationSnapshot.symbol == symbol,
            ValuationSnapshot.market == market,
        )
        item_count, last_updated_at = self.db.execute(stmt).one()
        return item_count, last_updated_at
