from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import (
    WatchlistEvaluationItem,
    WatchlistEvaluationSnapshot,
)
from app.adapters.llm.prompts.watchlist_evaluation import (
    WATCHLIST_EVALUATION_SYSTEM_PROMPT,
)
from app.adapters.llm.schema import ItemEvaluationResult, WatchlistEvaluationsResult
from app.adapters.llm.types import LLMTaskType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
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
    WatchlistEvaluationsResponse,
    WatchlistItemEvaluationProjection,
)
from app.domains.watchlists.types import (
    AiJudgment,
    NewsRisk,
    ThemeHeat,
    ValuationBurden,
)


class _ValidatedEvaluation(BaseModel):
    symbol: str
    news_risk: NewsRisk
    valuation_burden: ValuationBurden
    theme_heat: ThemeHeat
    ai_judgment: AiJudgment


class WatchlistEvaluationsService:
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
    ) -> WatchlistEvaluationsResponse:
        watchlist = self._get_owned_watchlist(watchlist_id, user_id)
        items = self._build_evaluation_items(watchlist.id)
        if not items:
            return WatchlistEvaluationsResponse(
                items=[],
                needs_research_count=0,
                cash_relevance_avg=0.0,
                generated_at=utc_now(),
            )

        snapshot = WatchlistEvaluationSnapshot(
            watchlist_id=watchlist.id,
            item_count=len(items),
            items=items,
        )
        result = WatchlistEvaluationsResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.WATCHLIST_EVALUATION,
                snapshot,
                WatchlistEvaluationsResult,
                WATCHLIST_EVALUATION_SYSTEM_PROMPT,
            ).output
        )
        projected_items = self._project_items(result.items, items)
        return WatchlistEvaluationsResponse(
            items=[
                WatchlistItemEvaluationProjection(
                    symbol=item.symbol,
                    news_risk=item.news_risk.value,
                    valuation_burden=item.valuation_burden.value,
                    theme_heat=item.theme_heat.value,
                    ai_judgment=item.ai_judgment.value,
                )
                for item in projected_items
            ],
            needs_research_count=sum(
                1
                for item in projected_items
                if item.news_risk is NewsRisk.HIGH
                or item.ai_judgment is AiJudgment.RISK_INCREASING
            ),
            cash_relevance_avg=(
                sum(1 for item in projected_items if item.ai_judgment is AiJudgment.WATCH)
                / len(projected_items)
                if projected_items
                else 0.0
            ),
            generated_at=utc_now(),
        )

    def _build_evaluation_items(
        self,
        watchlist_id: int,
    ) -> list[WatchlistEvaluationItem]:
        items = self.watchlist_item_repo.list_by_watchlist(watchlist_id)
        asset_ids = [item.asset_id for item in items]
        assets = {asset.id: asset for asset in self.asset_repo.list_by_ids(asset_ids)}
        active_types_by_asset = self.signal_repo.active_signal_types_by_asset(asset_ids)
        quotes = {
            quote.symbol.upper(): quote
            for quote in get_market_provider().get_quote(
                sorted({asset.symbol for asset in assets.values()})
            )
        } if assets else {}

        evaluation_items: list[WatchlistEvaluationItem] = []
        for item in items:
            asset = assets.get(item.asset_id)
            if asset is None:
                continue
            quote = quotes.get(asset.symbol.upper())
            evaluation_items.append(
                WatchlistEvaluationItem(
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
        return evaluation_items

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

    def _project_items(
        self,
        result_items: list[ItemEvaluationResult],
        snapshot_items: list[WatchlistEvaluationItem],
    ) -> list[_ValidatedEvaluation]:
        snapshot_symbols = {item.symbol for item in snapshot_items}
        projected: list[_ValidatedEvaluation] = []
        seen_symbols: set[str] = set()
        for item in result_items:
            if item.symbol not in snapshot_symbols or item.symbol in seen_symbols:
                continue
            projected.append(_ValidatedEvaluation.model_validate(item.model_dump()))
            seen_symbols.add(item.symbol)
        return projected
