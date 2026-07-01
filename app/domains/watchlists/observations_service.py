from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import (
    WatchlistHighlight,
    to_watchlist_observation_snapshot,
)
from app.adapters.llm.prompts.watchlist_observation import (
    WATCHLIST_OBSERVATION_SYSTEM_PROMPT,
)
from app.adapters.llm.schema import ObservationsResult
from app.adapters.llm.types import LLMTaskType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.signals.repository import SignalRepository
from app.domains.signals.time import utc_now
from app.domains.signals.types import resolve_watchlist_status
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.domains.watchlists.repository import (
    WatchlistItemRepository,
    WatchlistRepository,
)
from app.domains.watchlists.schema import WatchlistObservationsResponse


OBSERVATION_ITEM_LIMIT = 30


class WatchlistObservationsService:
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
    ) -> WatchlistObservationsResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        highlights = self._build_watchlist_highlights(watchlist.id)
        snapshot = to_watchlist_observation_snapshot(watchlist.id, highlights)
        result = ObservationsResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.WATCHLIST_NOTE,
                snapshot,
                ObservationsResult,
                WATCHLIST_OBSERVATION_SYSTEM_PROMPT,
            )
        )
        return WatchlistObservationsResponse(
            **result.model_dump(),
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

    def _build_watchlist_highlights(
        self,
        watchlist_id: int,
    ) -> list[WatchlistHighlight]:
        items = self._dedupe_top_watchlist_items(
            self.watchlist_item_repo.list_by_watchlist(watchlist_id, sort="priority"),
        )
        asset_ids = [item.asset_id for item in items]
        assets = {asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)}
        active_types_by_asset = self.signal_repo.active_signal_types_by_asset(asset_ids)
        quotes = {
            quote.symbol.upper(): quote
            for quote in get_market_provider().get_quote(
                sorted({asset.symbol for asset in assets.values()})
            )
        } if assets else {}

        highlights: list[WatchlistHighlight] = []
        for item in items:
            asset = assets.get(item.asset_id)
            if asset is None:
                continue
            quote = quotes.get(asset.symbol.upper())
            highlights.append(
                WatchlistHighlight(
                    symbol=asset.symbol,
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
        return highlights

    def _dedupe_top_watchlist_items(
        self,
        items: list[WatchlistItem],
    ) -> list[WatchlistItem]:
        selected: list[WatchlistItem] = []
        seen_asset_ids: set[int] = set()
        for item in items:
            if item.asset_id in seen_asset_ids:
                continue
            selected.append(item)
            seen_asset_ids.add(item.asset_id)
            if len(selected) == OBSERVATION_ITEM_LIMIT:
                break
        return selected
