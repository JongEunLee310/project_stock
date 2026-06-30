from decimal import Decimal

from sqlalchemy.orm import Session

from app.adapters.factory import get_market_provider
from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import to_briefing_snapshot
from app.adapters.llm.prompts.portfolio_briefing import PORTFOLIO_BRIEFING_SYSTEM_PROMPT
from app.adapters.llm.schema import BriefingResult
from app.adapters.llm.types import LLMTaskType
from app.domains.assets.repository import AssetRepository
from app.domains.portfolios.repository import PositionRepository
from app.domains.portfolios.schema import PortfolioBriefingResponse
from app.domains.portfolios.service import PortfolioService
from app.domains.signals.time import utc_now


class PortfolioBriefingService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.asset_repo = AssetRepository(db)
        self.position_repo = PositionRepository(db)
        self.portfolio_service = PortfolioService(db)
        self.gateway = gateway

    def generate(self, portfolio_id: int, user_id: int) -> PortfolioBriefingResponse:
        summary = self.portfolio_service.get_summary(portfolio_id, user_id)
        positions = self.position_repo.list_by_portfolio(portfolio_id)
        asset_ids = {position.asset_id for position in positions}
        assets = {
            asset.id: asset
            for asset in [self.asset_repo.get_by_id(asset_id) for asset_id in asset_ids]
            if asset is not None
        }
        quotes = {
            quote.symbol.upper(): quote
            for quote in get_market_provider().get_quote(
                sorted({asset.symbol for asset in assets.values()})
            )
        } if assets else {}

        symbol_by_asset_id = {
            asset_id: asset.symbol for asset_id, asset in assets.items()
        }
        sector_by_asset_id = {
            asset_id: asset.sector or "UNKNOWN" for asset_id, asset in assets.items()
        }
        daily_change_by_asset_id: dict[int, Decimal] = {}
        for asset_id, asset in assets.items():
            quote = quotes.get(asset.symbol.upper())
            daily_change_by_asset_id[asset_id] = (
                quote.change_percent if quote is not None else Decimal("0")
            )
        snapshot = to_briefing_snapshot(
            summary,
            symbol_by_asset_id=symbol_by_asset_id,
            sector_by_asset_id=sector_by_asset_id,
            daily_change_by_asset_id=daily_change_by_asset_id,
        )
        result = BriefingResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.PORTFOLIO_BRIEFING,
                snapshot,
                BriefingResult,
                PORTFOLIO_BRIEFING_SYSTEM_PROMPT,
            )
        )
        return PortfolioBriefingResponse(
            **result.model_dump(),
            generated_at=utc_now(),
        )
