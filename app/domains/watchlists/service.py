from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistResponse,
)


class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.item_repo = WatchlistItemRepository(db)

    def create_watchlist(
        self, user_id: int, data: WatchlistCreate
    ) -> WatchlistResponse:
        watchlist = self.watchlist_repo.create(user_id=user_id, name=data.name)
        return WatchlistResponse.model_validate(watchlist)

    def list_watchlists(self, user_id: int) -> list[WatchlistResponse]:
        return [
            WatchlistResponse.model_validate(watchlist)
            for watchlist in self.watchlist_repo.list_by_user(user_id)
        ]

    def add_item(
        self, watchlist_id: int, user_id: int, data: WatchlistItemCreate
    ) -> WatchlistItemResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(status_code=404, detail="종목을 찾을 수 없습니다.")
        if self.item_repo.get_by_watchlist_asset(watchlist.id, data.asset_id):
            raise AppException(status_code=400, detail="이미 관심 목록에 추가된 종목입니다.")
        try:
            item = self.item_repo.create(
                watchlist_id=watchlist.id,
                asset_id=data.asset_id,
                priority=data.priority,
            )
        except IntegrityError as exc:
            raise AppException(
                status_code=400, detail="이미 관심 목록에 추가된 종목입니다."
            ) from exc
        return WatchlistItemResponse.model_validate(item)

    def remove_item(self, watchlist_id: int, item_id: int, user_id: int) -> None:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        item = self.item_repo.get_by_id(item_id)
        if item is None or item.watchlist_id != watchlist.id:
            raise AppException(status_code=404, detail="관심 목록 종목을 찾을 수 없습니다.")
        self.item_repo.delete(item_id)

    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist:
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise AppException(status_code=404, detail="관심 목록을 찾을 수 없습니다.")
        if watchlist.user_id != user_id:
            raise AppException(status_code=403, detail="관심 목록 접근 권한이 없습니다.")
        return watchlist
