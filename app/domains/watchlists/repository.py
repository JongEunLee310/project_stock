from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.watchlists.model import Watchlist, WatchlistItem


class WatchlistRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, watchlist_id: int) -> Watchlist | None:
        return self.db.get(Watchlist, watchlist_id)

    def list_by_user(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Watchlist]:
        stmt = select(Watchlist).where(Watchlist.user_id == user_id).order_by(Watchlist.id)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Watchlist).where(Watchlist.user_id == user_id)
        return int(self.db.scalar(stmt) or 0)

    def create(self, user_id: int, name: str) -> Watchlist:
        watchlist = Watchlist(user_id=user_id, name=name)
        self.db.add(watchlist)
        self.db.commit()
        self.db.refresh(watchlist)
        return watchlist


class WatchlistItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, item_id: int) -> WatchlistItem | None:
        return self.db.get(WatchlistItem, item_id)

    def get_by_watchlist_asset(
        self, watchlist_id: int, asset_id: int
    ) -> WatchlistItem | None:
        stmt = select(WatchlistItem).where(
            WatchlistItem.watchlist_id == watchlist_id,
            WatchlistItem.asset_id == asset_id,
        )
        return self.db.scalars(stmt).first()

    def list_by_watchlist(self, watchlist_id: int) -> list[WatchlistItem]:
        stmt = (
            select(WatchlistItem)
            .where(WatchlistItem.watchlist_id == watchlist_id)
            .order_by(WatchlistItem.priority, WatchlistItem.id)
        )
        return list(self.db.scalars(stmt).all())

    def create(self, watchlist_id: int, asset_id: int, priority: int) -> WatchlistItem:
        item = WatchlistItem(
            watchlist_id=watchlist_id,
            asset_id=asset_id,
            priority=priority,
        )
        self.db.add(item)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(item)
        return item

    def delete(self, item_id: int) -> None:
        item = self.get_by_id(item_id)
        if item is None:
            return
        self.db.delete(item)
        self.db.commit()
