from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset


class AssetRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, asset_id: int) -> Asset | None:
        return self.db.get(Asset, asset_id)

    def get_by_symbol_market(self, symbol: str, market: str) -> Asset | None:
        stmt = select(Asset).where(Asset.symbol == symbol, Asset.market == market)
        return self.db.scalars(stmt).first()

    def list_all(
        self,
        is_active: bool | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Asset]:
        stmt = select(Asset).order_by(Asset.id)
        if is_active is not None:
            stmt = stmt.where(Asset.is_active == is_active)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_all(self, is_active: bool | None = None) -> int:
        stmt = select(func.count()).select_from(Asset)
        if is_active is not None:
            stmt = stmt.where(Asset.is_active == is_active)
        return int(self.db.scalar(stmt) or 0)

    def create(self, symbol: str, name: str, market: str) -> Asset:
        asset = Asset(symbol=symbol, name=name, market=market)
        self.db.add(asset)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(asset)
        return asset
