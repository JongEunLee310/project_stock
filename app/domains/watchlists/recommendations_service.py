from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import (
    StockRecommendationCandidate,
    to_stock_recommendation_snapshot,
)
from app.adapters.llm.prompts.stock_recommendation import (
    STOCK_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.adapters.llm.schema import StockRecommendationResult
from app.adapters.llm.types import LLMTaskType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.time import utc_now
from app.domains.signals.types import resolve_watchlist_status
from app.domains.watchlists.model import Watchlist
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import (
    StockRecommendationProjection,
    WatchlistRecommendationsResponse,
)


RECOMMENDATION_CANDIDATE_LIMIT = 20
RECOMMENDATION_MAX_ITEMS = 5


class WatchlistRecommendationsService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.asset_repo = AssetRepository(db)
        self.signal_repo = SignalRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.watchlist_item_repo = WatchlistItemRepository(db)
        self.gateway = gateway

    def generate(
        self,
        watchlist_id: int,
        user_id: int,
    ) -> WatchlistRecommendationsResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        current_assets = self._list_current_assets(watchlist.id)
        current_asset_ids = {asset.id for asset in current_assets}
        current_symbols = [asset.symbol for asset in current_assets]
        candidate_assets = [
            asset
            for asset in self.asset_repo.list_all(is_active=True)
            if asset.id not in current_asset_ids
        ][:RECOMMENDATION_CANDIDATE_LIMIT]

        if not candidate_assets:
            return WatchlistRecommendationsResponse(
                recommendations=[],
                generated_at=utc_now(),
            )

        candidates = self._build_candidates(candidate_assets)
        snapshot = to_stock_recommendation_snapshot(
            watchlist.id,
            current_symbols,
            candidates,
        )
        result = StockRecommendationResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.STOCK_RECOMMENDATION,
                snapshot,
                StockRecommendationResult,
                STOCK_RECOMMENDATION_SYSTEM_PROMPT,
            ).output
        )
        recommendations = self._project_recommendations(result, candidate_assets)
        return WatchlistRecommendationsResponse(
            recommendations=recommendations,
            generated_at=utc_now(),
        )

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

    def _list_current_assets(self, watchlist_id: int) -> list[Asset]:
        items = self.watchlist_item_repo.list_by_watchlist(watchlist_id)
        asset_ids = [item.asset_id for item in items]
        return self.asset_repo.list_by_ids(asset_ids)

    def _build_candidates(
        self,
        candidate_assets: list[Asset],
    ) -> list[StockRecommendationCandidate]:
        asset_ids = [asset.id for asset in candidate_assets]
        active_types_by_asset = self.signal_repo.active_signal_types_by_asset(asset_ids)
        quotes = {
            quote.symbol.upper(): quote
            for quote in get_market_provider().get_quote(
                [asset.symbol for asset in candidate_assets]
            )
        }

        candidates: list[StockRecommendationCandidate] = []
        for asset in candidate_assets:
            quote = quotes.get(asset.symbol.upper())
            candidates.append(
                StockRecommendationCandidate(
                    symbol=asset.symbol,
                    name=asset.name,
                    sector=asset.sector,
                    status=resolve_watchlist_status(
                        active_types_by_asset.get(asset.id, set())
                    ),
                    per=quote.per if quote is not None else None,
                    peg=quote.peg if quote is not None else None,
                    daily_change_percent=(
                        quote.change_percent if quote is not None else Decimal("0")
                    ),
                )
            )
        return candidates

    def _project_recommendations(
        self,
        result: StockRecommendationResult,
        candidate_assets: list[Asset],
    ) -> list[StockRecommendationProjection]:
        assets_by_symbol = {asset.symbol: asset for asset in candidate_assets}
        projections: list[StockRecommendationProjection] = []
        seen_symbols: set[str] = set()
        for item in result.recommendations:
            if len(projections) == RECOMMENDATION_MAX_ITEMS:
                break
            asset = assets_by_symbol.get(item.symbol)
            if asset is None or item.symbol in seen_symbols:
                continue
            projections.append(
                StockRecommendationProjection(
                    symbol=item.symbol,
                    name=asset.name,
                    rationale=item.rationale,
                    reference_metrics=item.reference_metrics,
                )
            )
            seen_symbols.add(item.symbol)
        return projections
