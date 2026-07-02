import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.portfolios.model import Position
from app.domains.watchlists.model import WatchlistItem

logger = logging.getLogger(__name__)


class NewsUniverseResolver:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(self, symbols: list[str] | None = None) -> list[tuple[str, str, str]]:
        if symbols is not None:
            return self._asset_targets(symbols)

        targets: dict[tuple[str, str], tuple[str, str, str]] = {}
        for symbol, market, name in (
            self._watchlist_targets() + self._portfolio_targets()
        ):
            normalized_symbol = symbol.upper()
            normalized_market = market.upper()
            targets[(normalized_symbol, normalized_market)] = (
                normalized_symbol,
                normalized_market,
                name,
            )
        return list(targets.values())

    def _asset_targets(self, symbols: list[str]) -> list[tuple[str, str, str]]:
        normalized_symbols = sorted({symbol.upper() for symbol in symbols})
        if not normalized_symbols:
            return []

        stmt = (
            select(Asset.symbol, Asset.market, Asset.name)
            .where(func.upper(Asset.symbol).in_(normalized_symbols))
            .where(Asset.is_active.is_(True))
            .order_by(Asset.symbol, Asset.market)
        )
        targets = [
            (symbol.upper(), market.upper(), name)
            for symbol, market, name in self.db.execute(stmt).all()
        ]
        found_symbols = {symbol for symbol, _, _ in targets}
        missing_symbols = set(normalized_symbols) - found_symbols
        for symbol in sorted(missing_symbols):
            logger.warning("Skipping unknown news target symbol", extra={"symbol": symbol})
        return targets

    def _watchlist_targets(self) -> list[tuple[str, str, str]]:
        stmt = (
            select(Asset.symbol, Asset.market, Asset.name)
            .join(WatchlistItem, WatchlistItem.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.symbol, Asset.market)
        )
        return [
            (symbol, market, name)
            for symbol, market, name in self.db.execute(stmt).all()
        ]

    def _portfolio_targets(self) -> list[tuple[str, str, str]]:
        stmt = (
            select(Asset.symbol, Asset.market, Asset.name)
            .join(Position, Position.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.symbol, Asset.market)
        )
        return [
            (symbol, market, name)
            for symbol, market, name in self.db.execute(stmt).all()
        ]
