from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.benchmark.sector_map import resolve_sector_etf
from app.domains.portfolios.model import Position
from app.domains.watchlists.model import WatchlistItem


class PriceUniverseResolver:
    def __init__(self, db: Session) -> None:
        self.db = db

    def resolve(self) -> list[tuple[str, str]]:
        return self._deduplicate([*self.resolve_assets(), *self._benchmark_targets()])

    def resolve_assets(self) -> list[tuple[str, str]]:
        return self._deduplicate(self._watchlist_targets() + self._portfolio_targets())

    @staticmethod
    def _deduplicate(all_targets: list[tuple[str, str]]) -> list[tuple[str, str]]:
        targets: dict[tuple[str, str], None] = {}
        for symbol, market in all_targets:
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

    def _benchmark_targets(self) -> list[tuple[str, str]]:
        mapped_targets: dict[tuple[str, str], None] = {}
        needs_fallback = False
        sectors = self._watchlist_sectors() + self._portfolio_sectors()
        for sector in sectors:
            symbol, market, _ = resolve_sector_etf(sector)
            if symbol == "SPY":
                needs_fallback = True
                continue
            mapped_targets[(symbol, market)] = None

        targets = [("QQQ", "NASDAQ"), *mapped_targets]
        if needs_fallback:
            targets.append(("SPY", "NYSE"))
        return targets

    def _watchlist_sectors(self) -> list[str | None]:
        stmt = (
            select(Asset.sector)
            .join(WatchlistItem, WatchlistItem.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.sector)
        )
        return list(self.db.scalars(stmt).all())

    def _portfolio_sectors(self) -> list[str | None]:
        stmt = (
            select(Asset.sector)
            .join(Position, Position.asset_id == Asset.id)
            .where(Asset.is_active.is_(True))
            .order_by(Asset.sector)
        )
        return list(self.db.scalars(stmt).all())
