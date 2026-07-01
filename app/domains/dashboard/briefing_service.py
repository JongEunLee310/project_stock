from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import WatchlistHighlight, to_dashboard_snapshot
from app.adapters.llm.prompts.dashboard_briefing import DASHBOARD_BRIEFING_SYSTEM_PROMPT
from app.adapters.llm.schema import BriefingResult
from app.adapters.llm.types import LLMTaskType
from app.domains.assets.repository import AssetRepository
from app.domains.dashboard.schema import DashboardBriefingResponse
from app.domains.dashboard.service import DashboardService
from app.domains.signals.repository import SignalRepository
from app.domains.signals.time import utc_now
from app.domains.signals.types import resolve_watchlist_status
from app.domains.watchlists.model import WatchlistItem
from app.domains.watchlists.repository import WatchlistItemRepository


WATCHLIST_HIGHLIGHT_LIMIT = 5


class DashboardBriefingService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.asset_repo = AssetRepository(db)
        self.dashboard_service = DashboardService(db)
        self.signal_repo = SignalRepository(db)
        self.watchlist_item_repo = WatchlistItemRepository(db)
        self.gateway = gateway

    def generate(self, user_id: int) -> DashboardBriefingResponse:
        summary = self.dashboard_service.get_summary(user_id)
        highlights = self._build_watchlist_highlights(user_id)
        snapshot = to_dashboard_snapshot(summary, highlights=highlights)
        result = BriefingResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.DASHBOARD_BRIEFING,
                snapshot,
                BriefingResult,
                DASHBOARD_BRIEFING_SYSTEM_PROMPT,
            )
        )
        return DashboardBriefingResponse(
            **result.model_dump(),
            generated_at=utc_now(),
        )

    def _build_watchlist_highlights(self, user_id: int) -> list[WatchlistHighlight]:
        items = self._dedupe_top_watchlist_items(
            self.watchlist_item_repo.list_by_user(user_id),
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
            if len(selected) == WATCHLIST_HIGHLIGHT_LIMIT:
                break
        return selected
