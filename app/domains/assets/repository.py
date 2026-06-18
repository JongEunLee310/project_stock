from sqlalchemy import select
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

    def list_all(self, is_active: bool | None = None) -> list[Asset]:
        stmt = select(Asset).order_by(Asset.id)
        if is_active is not None:
            stmt = stmt.where(Asset.is_active == is_active)
        return list(self.db.scalars(stmt).all())

    def create(self, symbol: str, name: str, market: str) -> Asset:
        asset = Asset(symbol=symbol, name=name, market=market)
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        return asset
