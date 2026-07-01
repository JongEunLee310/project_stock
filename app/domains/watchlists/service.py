from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.types import SignalType
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import (
    AssetBriefResponse,
    RecentWatchlistItemResponse,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemExpandedResponse,
    WatchlistItemResponse,
    WatchlistResponse,
    WatchlistSummaryResponse,
)


class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.signal_repo = SignalRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.item_repo = WatchlistItemRepository(db)

    def create_watchlist(
        self, user_id: int, data: WatchlistCreate
    ) -> WatchlistResponse:
        watchlist = self.watchlist_repo.create(user_id=user_id, name=data.name)
        return WatchlistResponse.model_validate(watchlist)

    def list_watchlists(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[WatchlistResponse]:
        return [
            WatchlistResponse.model_validate(watchlist)
            for watchlist in self.watchlist_repo.list_by_user(
                user_id,
                offset=offset,
                limit=limit,
            )
        ]

    def count_watchlists(self, user_id: int) -> int:
        return self.watchlist_repo.count_by_user(user_id)

    def add_item(
        self, watchlist_id: int, user_id: int, data: WatchlistItemCreate
    ) -> WatchlistItemResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        if self.item_repo.get_by_watchlist_asset(watchlist.id, data.asset_id):
            raise AppException(
                status_code=400,
                detail="이미 관심 목록에 추가된 종목입니다.",
                error_code=ErrorCode.WATCHLIST_ITEM_DUPLICATE,
            )
        try:
            item = self.item_repo.create(
                watchlist_id=watchlist.id,
                asset_id=data.asset_id,
                priority=data.priority,
                reason=data.reason,
                tags=data.tags,
                memo=data.memo,
            )
        except IntegrityError as exc:
            raise AppException(
                status_code=400,
                detail="이미 관심 목록에 추가된 종목입니다.",
                error_code=ErrorCode.WATCHLIST_ITEM_DUPLICATE,
            ) from exc
        return WatchlistItemResponse.model_validate(item)

    def list_items(
        self,
        watchlist_id: int,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "priority",
    ) -> list[WatchlistItemResponse]:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        return [
            WatchlistItemResponse.model_validate(item)
            for item in self.item_repo.list_by_watchlist(
                watchlist.id,
                offset=offset,
                limit=limit,
                sort=sort,
            )
        ]

    def list_items_expanded(
        self,
        watchlist_id: int,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "priority",
    ) -> list[WatchlistItemExpandedResponse]:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        items = self.item_repo.list_by_watchlist(
            watchlist.id,
            offset=offset,
            limit=limit,
            sort=sort,
        )
        asset_ids = [item.asset_id for item in items]
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(aid) for aid in asset_ids]
            if asset is not None
        }
        symbols = [asset.symbol for asset in assets.values()]
        quotes = {
            q.symbol: q
            for q in get_market_provider().get_quote(symbols)
        } if symbols else {}

        result = []
        for item in items:
            asset = assets.get(item.asset_id)
            asset_brief: AssetBriefResponse | None = None
            if asset is not None:
                quote = quotes.get(asset.symbol)
                asset_brief = AssetBriefResponse(
                    symbol=asset.symbol,
                    market=asset.market,
                    name=asset.name,
                    price=str(quote.price) if quote is not None else "0",
                    change_percent=str(quote.change_percent) if quote is not None else "0",
                    sector=asset.sector,
                )
            item_data = WatchlistItemResponse.model_validate(item).model_dump()
            result.append(WatchlistItemExpandedResponse(**item_data, asset=asset_brief))
        return result

    def count_items(self, watchlist_id: int, user_id: int) -> int:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        return self.item_repo.count_by_watchlist(watchlist.id)

    def get_summary(
        self,
        watchlist_id: int,
        user_id: int,
        recent_limit: int = 5,
    ) -> WatchlistSummaryResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        total_count = self.item_repo.count_by_watchlist(watchlist.id)
        items = self.item_repo.list_by_watchlist(watchlist.id)
        asset_ids = [item.asset_id for item in items]
        risk_increasing_count = self.signal_repo.count_assets_with_active_signal(
            asset_ids,
            SignalType.RISK_ALERT.value,
        )
        recent_items = self.item_repo.list_by_watchlist(
            watchlist.id,
            limit=recent_limit,
            sort="-created_at",
        )
        recent_asset_ids = [item.asset_id for item in recent_items]
        assets = {
            asset.id: asset
            for asset in [
                self.asset_repo.get_by_id(asset_id) for asset_id in recent_asset_ids
            ]
            if asset is not None
        }
        return WatchlistSummaryResponse(
            total_count=total_count,
            risk_increasing_count=risk_increasing_count,
            recent_items=[
                RecentWatchlistItemResponse(
                    symbol=asset.symbol,
                    name=asset.name,
                    created_at=item.created_at,
                )
                for item in recent_items
                if (asset := assets.get(item.asset_id)) is not None
            ],
        )

    def remove_item(self, watchlist_id: int, item_id: int, user_id: int) -> None:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        item = self.item_repo.get_by_id(item_id)
        if item is None or item.watchlist_id != watchlist.id:
            raise AppException(
                status_code=404,
                detail="관심 목록 종목을 찾을 수 없습니다.",
                error_code=ErrorCode.WATCHLIST_ITEM_NOT_FOUND,
            )
        self.item_repo.delete(item_id)

    def _get_owned_watchlist(self, watchlist_id: int, user_id: int) -> Watchlist:
        watchlist = self.watchlist_repo.get_by_id(watchlist_id)
        if watchlist is None:
            raise AppException(
                status_code=404,
                detail="관심 목록을 찾을 수 없습니다.",
                error_code=ErrorCode.WATCHLIST_NOT_FOUND,
            )
        if watchlist.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="관심 목록 접근 권한이 없습니다.",
                error_code=ErrorCode.WATCHLIST_FORBIDDEN,
            )
        return watchlist
