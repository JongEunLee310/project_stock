from decimal import Decimal
from typing import Iterable

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.adapters.market.base import QuoteResult
from app.adapters.factory import get_market_provider
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.portfolios.model import Portfolio, Position
from app.domains.portfolios.repository import PortfolioRepository, PositionRepository
from app.domains.portfolios.schema import (
    PortfolioCheckResponse,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionCreate,
    PositionWeight,
    PositionResponse,
    PositionUpdate,
    SectorWeight,
    RiskExposure,
)
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate, SignalResponse
from app.domains.signals.types import SignalType


RISK_LEVEL_HIGH_MULTIPLIER = Decimal("1.5")
CASH_FLOOR_HIGH = Decimal("0.05")
CASH_FLOOR_MEDIUM = Decimal("0.15")


class PortfolioService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.position_repo = PositionRepository(db)
        self.signal_repo = SignalRepository(db)

    def create_portfolio(
        self, user_id: int, data: PortfolioCreate
    ) -> PortfolioResponse:
        portfolio = self.portfolio_repo.create(user_id=user_id, data=data)
        return PortfolioResponse.model_validate(portfolio)

    def list_portfolios(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[PortfolioResponse]:
        return [
            PortfolioResponse.model_validate(portfolio)
            for portfolio in self.portfolio_repo.list_by_user(
                user_id,
                offset=offset,
                limit=limit,
            )
        ]

    def count_portfolios(self, user_id: int) -> int:
        return self.portfolio_repo.count_by_user(user_id)

    def add_position(
        self, portfolio_id: int, user_id: int, data: PositionCreate
    ) -> PositionResponse:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        if self.position_repo.get_by_portfolio_asset(portfolio.id, data.asset_id):
            raise AppException(
                status_code=400,
                detail="이미 포트폴리오에 추가된 종목입니다.",
                error_code=ErrorCode.POSITION_DUPLICATE,
            )
        try:
            position = self.position_repo.create(portfolio.id, data)
        except IntegrityError as exc:
            raise AppException(
                status_code=400,
                detail="이미 포트폴리오에 추가된 종목입니다.",
                error_code=ErrorCode.POSITION_DUPLICATE,
            ) from exc
        return PositionResponse.model_validate(position)

    def update_position(
        self,
        portfolio_id: int,
        position_id: int,
        user_id: int,
        data: PositionUpdate,
    ) -> PositionResponse:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        position = self.position_repo.get_by_id(position_id)
        if position is None or position.portfolio_id != portfolio.id:
            raise AppException(
                status_code=404,
                detail="보유 종목을 찾을 수 없습니다.",
                error_code=ErrorCode.POSITION_NOT_FOUND,
            )
        updated_position = self.position_repo.update(position, data)
        return PositionResponse.model_validate(updated_position)

    def remove_position(
        self, portfolio_id: int, position_id: int, user_id: int
    ) -> None:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        position = self.position_repo.get_by_id(position_id)
        if position is None or position.portfolio_id != portfolio.id:
            raise AppException(
                status_code=404,
                detail="보유 종목을 찾을 수 없습니다.",
                error_code=ErrorCode.POSITION_NOT_FOUND,
            )
        self.position_repo.delete(position_id)

    def get_summary(
        self,
        portfolio_id: int,
        user_id: int,
    ) -> PortfolioSummaryResponse:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        return self._build_summary(portfolio)

    def check_concentration(
        self,
        portfolio_id: int,
        user_id: int,
    ) -> PortfolioCheckResponse:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        summary = self._build_summary(portfolio)
        created_signals: list[SignalResponse] = []

        for position in summary.positions:
            if not position.exceeds_threshold:
                continue
            exists_active = self.signal_repo.exists_active(
                position.asset_id,
                SignalType.RISK_ALERT.value,
                None,
            )
            if exists_active:
                continue

            signal = self.signal_repo.create(
                SignalCreate(
                    asset_id=position.asset_id,
                    signal_type=SignalType.RISK_ALERT,
                    score=self._score_from_weight(position.weight),
                    risk_level="HIGH",
                    reason="포트폴리오 단일 종목 비중이 임계치를 초과했습니다.",
                    evidence={
                        "portfolio_id": portfolio.id,
                        "weight": str(position.weight),
                        "threshold": str(summary.concentration_threshold),
                        "cost_value": str(position.cost_value),
                        "market_value": str(position.market_value),
                    },
                )
            )
            created_signals.append(SignalResponse.model_validate(signal))

        return PortfolioCheckResponse(
            summary=summary,
            created_signals=created_signals,
        )

    def _get_owned_portfolio(self, portfolio_id: int, user_id: int) -> Portfolio:
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise AppException(
                status_code=404,
                detail="포트폴리오를 찾을 수 없습니다.",
                error_code=ErrorCode.PORTFOLIO_NOT_FOUND,
            )
        if portfolio.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="포트폴리오 접근 권한이 없습니다.",
                error_code=ErrorCode.PORTFOLIO_FORBIDDEN,
            )
        return portfolio

    def _build_summary(self, portfolio: Portfolio) -> PortfolioSummaryResponse:
        positions = self.position_repo.list_by_portfolio(portfolio.id)
        assets_by_id = self._get_assets_by_position(positions)
        (
            total_cost_value,
            total_value,
            position_weights,
            sector_weights,
            day_change_value,
            day_change_percent,
        ) = self._calculate_weights(
            positions,
            assets_by_id,
            portfolio.cash_balance,
            portfolio.concentration_threshold,
        )
        cash_weight = self._calculate_weight(portfolio.cash_balance, total_value)
        risk_exposures = self._calculate_risk_exposures(
            sector_weights=sector_weights,
            position_weights=position_weights,
            assets_by_id=assets_by_id,
            cash_weight=cash_weight,
            total_value=total_value,
            concentration_threshold=portfolio.concentration_threshold,
        )
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            concentration_threshold=portfolio.concentration_threshold,
            total_cost_value=total_cost_value,
            total_value=total_value,
            cash_balance=portfolio.cash_balance,
            cash_weight=cash_weight,
            has_sector_concentration=any(
                sector_weight.exceeds_threshold for sector_weight in sector_weights
            ),
            positions=position_weights,
            sector_weights=sector_weights,
            day_change_value=day_change_value,
            day_change_percent=day_change_percent,
            risk_exposures=risk_exposures,
        )

    def _get_assets_by_position(self, positions: list[Position]) -> dict[int, Asset]:
        asset_ids = {position.asset_id for position in positions}
        assets: dict[int, Asset] = {}
        for asset_id in asset_ids:
            asset = self.asset_repo.get_by_id(asset_id)
            if asset is not None:
                assets[asset_id] = asset
        return assets

    def _calculate_weights(
        self,
        positions: list[Position],
        assets_by_id: dict[int, Asset],
        cash_balance: Decimal,
        threshold: Decimal,
    ) -> tuple[
        Decimal,
        Decimal,
        list[PositionWeight],
        list[SectorWeight],
        Decimal,
        Decimal,
    ]:
        costs = [position.quantity * position.avg_buy_price for position in positions]
        total_cost_value = sum(costs, Decimal("0"))
        quotes_by_symbol = self._get_quotes_by_symbol(assets_by_id.values())
        market_values: list[Decimal] = []
        day_change_values: list[Decimal] = []
        sector_market_values: dict[str, Decimal] = {}

        for position in positions:
            asset = assets_by_id.get(position.asset_id)
            price = Decimal("0")
            change_percent = Decimal("0")
            sector = "UNKNOWN"
            if asset is not None:
                quote = quotes_by_symbol.get(asset.symbol.upper())
                if quote is not None:
                    price = quote.price
                    change_percent = quote.change_percent
                sector = asset.sector or "UNKNOWN"
            market_value = position.quantity * price
            market_values.append(market_value)
            day_change_values.append(
                self._calculate_position_day_change(market_value, price, change_percent)
            )
            sector_market_values[sector] = (
                sector_market_values.get(sector, Decimal("0")) + market_value
            )

        total_market_value = sum(market_values, Decimal("0"))
        total_value = total_market_value + cash_balance
        day_change_value = sum(day_change_values, Decimal("0"))
        prev_total_value = total_value - day_change_value
        day_change_percent = (
            Decimal("0")
            if prev_total_value == 0
            else (day_change_value / prev_total_value) * Decimal("100")
        )
        weights: list[PositionWeight] = []

        for position, cost_value, market_value in zip(
            positions,
            costs,
            market_values,
            strict=True,
        ):
            weight = self._calculate_weight(market_value, total_value)
            weights.append(
                PositionWeight(
                    asset_id=position.asset_id,
                    quantity=position.quantity,
                    avg_buy_price=position.avg_buy_price,
                    cost_value=cost_value,
                    market_value=market_value,
                    cost_weight=self._calculate_weight(cost_value, total_cost_value),
                    weight=weight,
                    exceeds_threshold=weight > threshold,
                )
            )

        sector_weights: list[SectorWeight] = []
        for sector, market_value in sorted(sector_market_values.items()):
            sector_weight = self._calculate_weight(market_value, total_value)
            sector_weights.append(
                SectorWeight(
                    sector=sector,
                    market_value=market_value,
                    weight=sector_weight,
                    exceeds_threshold=sector_weight > threshold,
                )
            )

        return (
            total_cost_value,
            total_value,
            weights,
            sector_weights,
            day_change_value,
            day_change_percent,
        )

    def _get_quotes_by_symbol(self, assets: Iterable[Asset]) -> dict[str, QuoteResult]:
        symbols = sorted({asset.symbol.upper() for asset in assets})
        if not symbols:
            return {}
        return {
            quote.symbol.upper(): quote
            for quote in get_market_provider().get_quote(symbols)
        }

    def _calculate_position_day_change(
        self,
        market_value: Decimal,
        price: Decimal,
        change_percent: Decimal,
    ) -> Decimal:
        denominator = Decimal("1") + change_percent / Decimal("100")
        if price == 0 or denominator == 0:
            return Decimal("0")
        prev_value = market_value / denominator
        return market_value - prev_value

    def _calculate_weight(self, value: Decimal, total_value: Decimal) -> Decimal:
        if total_value == 0:
            return Decimal("0")
        return value / total_value

    def _calculate_risk_exposures(
        self,
        *,
        sector_weights: list[SectorWeight],
        position_weights: list[PositionWeight],
        assets_by_id: dict[int, Asset],
        cash_weight: Decimal,
        total_value: Decimal,
        concentration_threshold: Decimal,
    ) -> list[RiskExposure]:
        high_threshold = concentration_threshold * RISK_LEVEL_HIGH_MULTIPLIER
        risk_exposures: list[RiskExposure] = []

        concentrated_sectors = sorted(
            (
                sector_weight
                for sector_weight in sector_weights
                if sector_weight.exceeds_threshold
                and sector_weight.sector != "UNKNOWN"
            ),
            key=lambda sector_weight: (
                -sector_weight.weight,
                sector_weight.sector,
            ),
        )
        for sector_weight in concentrated_sectors:
            risk_exposures.append(
                RiskExposure(
                    code=f"SECTOR_CONCENTRATION:{sector_weight.sector}",
                    label=f"{sector_weight.sector} 섹터 쏠림",
                    level=self._risk_level(sector_weight.weight, high_threshold),
                    description=(
                        f"{sector_weight.sector} 섹터 비중이 "
                        f"{sector_weight.weight:.2%}로 임계값 "
                        f"{concentration_threshold:.2%}을 초과합니다."
                    ),
                )
            )

        concentrated_positions = sorted(
            (
                (position_weight, assets_by_id.get(position_weight.asset_id))
                for position_weight in position_weights
                if position_weight.exceeds_threshold
            ),
            key=lambda item: (
                -item[0].weight,
                item[1].symbol if item[1] is not None else str(item[0].asset_id),
            ),
        )
        for position_weight, asset in concentrated_positions:
            symbol = asset.symbol if asset is not None else str(position_weight.asset_id)
            risk_exposures.append(
                RiskExposure(
                    code=f"SINGLE_NAME_CONCENTRATION:{symbol}",
                    label=f"{symbol} 단일 종목 쏠림",
                    level=self._risk_level(position_weight.weight, high_threshold),
                    description=(
                        f"{symbol} 비중이 {position_weight.weight:.2%}로 임계값 "
                        f"{concentration_threshold:.2%}을 초과합니다."
                    ),
                )
            )

        if total_value != 0:
            cash_level: str | None = None
            if cash_weight < CASH_FLOOR_HIGH:
                cash_level = "HIGH"
            elif cash_weight < CASH_FLOOR_MEDIUM:
                cash_level = "MEDIUM"

            if cash_level is not None:
                risk_exposures.append(
                    RiskExposure(
                        code="CASH_SHORTAGE",
                        label="현금 비중 부족",
                        level=cash_level,
                        description=(
                            f"현금 비중이 {cash_weight:.2%}로 낮아 "
                            "변동성 대응 여력이 제한될 수 있습니다."
                        ),
                    )
                )

        return risk_exposures

    def _risk_level(self, weight: Decimal, high_threshold: Decimal) -> str:
        if weight >= high_threshold:
            return "HIGH"
        return "MEDIUM"

    def _score_from_weight(self, weight: Decimal) -> int:
        return max(0, min(100, int(weight * Decimal("100"))))
