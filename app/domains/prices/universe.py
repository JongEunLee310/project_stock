from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.portfolios.model import Position
from app.domains.watchlists.model import WatchlistItem


class PriceUniverseResolver:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(self) -> list[tuple[str, str]]:
        targets: dict[tuple[str, str], None] = {}
        for symbol, market in self._watchlist_targets() + self._portfolio_targets():
            targets[(symbol.upper(), market.upper())] = None
        return list(targets)

    def _watchlist_targets(self) -> list[tuple[str, str]]:
        stmt = (
            select(Asset.symbol, Asset.market)
            .join(WatchlistItem, WatchlistItem.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.symbol, Asset.market)
        )
        return [(symbol, market) for symbol, market in self.db.execute(stmt).all()]

    def _portfolio_targets(self) -> list[tuple[str, str]]:
        stmt = (
            select(Asset.symbol, Asset.market)
            .join(Position, Position.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.symbol, Asset.market)
        )
        return [(symbol, market) for symbol, market in self.db.execute(stmt).all()]
