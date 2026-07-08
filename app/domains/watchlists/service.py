from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.portfolios.repository import PortfolioRepository
from app.domains.portfolios.service import (
    CASH_FLOOR_HIGH,
    CASH_FLOOR_MEDIUM,
    PortfolioService,
)
from app.domains.signals.repository import SignalRepository
from app.domains.signals.types import SignalType, resolve_watchlist_status
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import (
    AssetBriefResponse,
    BuyReadinessProjection,
    RecentWatchlistItemResponse,
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemExpandedResponse,
    WatchlistItemResponse,
    WatchlistResponse,
    WatchlistSummaryResponse,
)
from app.domains.watchlists.types import BuyReadinessLevel


class WatchlistService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.asset_repo = AssetRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
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
        active_types = self.signal_repo.active_signal_types_by_asset(asset_ids)

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
                    currency=quote.currency if quote is not None else None,
                    reference_at=quote.as_of if quote is not None else None,
                )
            item_data = WatchlistItemResponse.model_validate(item).model_dump()
            result.append(
                WatchlistItemExpandedResponse(
                    **item_data,
                    status=resolve_watchlist_status(
                        active_types.get(item.asset_id, set())
                    ),
                    asset=asset_brief,
                )
            )
        return result

    def count_items(self, watchlist_id: int, user_id: int) -> int:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        return self.item_repo.count_by_watchlist(watchlist.id)

    def get_summary(
        self,
        watchlist_id: int,
        user_id: int,
        portfolio_id: int | None = None,
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
            buy_readiness=self._build_buy_readiness(
                asset_ids=asset_ids,
                user_id=user_id,
                portfolio_id=portfolio_id,
            ),
        )

    def _build_buy_readiness(
        self,
        *,
        asset_ids: list[int],
        user_id: int,
        portfolio_id: int | None,
    ) -> BuyReadinessProjection | None:
        resolved_portfolio_id = portfolio_id
        if resolved_portfolio_id is None:
            portfolios = self.portfolio_repo.list_by_user(user_id, limit=1)
            if not portfolios:
                return None
            resolved_portfolio_id = portfolios[0].id

        portfolio_summary = PortfolioService(self.db).get_summary(
            resolved_portfolio_id,
            user_id,
        )
        buy_candidate_count = self.signal_repo.count_assets_with_active_signal(
            asset_ids,
            SignalType.BUY_CANDIDATE.value,
        )
        level = self._buy_readiness_level(portfolio_summary.cash_weight)
        level_label = self._buy_readiness_label(level)
        return BuyReadinessProjection(
            level=level.value,
            level_label=level_label,
            cash_weight=portfolio_summary.cash_weight,
            buy_candidate_count=buy_candidate_count,
            message=(
                f"현금 비중은 {portfolio_summary.cash_weight:.1%}입니다. "
                f"매수 검토 후보는 {buy_candidate_count}개이며, "
                f"신규 매수 여력은 {level_label}입니다."
            ),
        )

    def _buy_readiness_level(self, cash_weight: Decimal) -> BuyReadinessLevel:
        if cash_weight >= CASH_FLOOR_MEDIUM:
            return BuyReadinessLevel.SUFFICIENT
        if cash_weight >= CASH_FLOOR_HIGH:
            return BuyReadinessLevel.LIMITED
        return BuyReadinessLevel.RESTRICTED

    def _buy_readiness_label(self, level: BuyReadinessLevel) -> str:
        labels = {
            BuyReadinessLevel.SUFFICIENT: "충분",
            BuyReadinessLevel.LIMITED: "제한적",
            BuyReadinessLevel.RESTRICTED: "매우 제한적",
        }
        return labels[level]

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
