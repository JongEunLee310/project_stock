from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.raw_prices.model import RawPrice
from app.domains.raw_prices.schema import RawPriceCreate


class RawPriceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def save(self, data: RawPriceCreate) -> RawPrice | None:
        raw_price = RawPrice(**data.model_dump(exclude_none=True))
        self.db.add(raw_price)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None
        self.db.refresh(raw_price)
        return raw_price

    def exists_by_hash(self, payload_hash: str) -> bool:
        stmt = select(RawPrice.id).where(RawPrice.payload_hash == payload_hash)
        return self.db.scalar(stmt) is not None
