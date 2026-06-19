from decimal import Decimal

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.portfolios.model import Portfolio, Position
from app.domains.portfolios.repository import PortfolioRepository, PositionRepository
from app.domains.portfolios.schema import (
    PortfolioCheckResponse,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionWeight,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)
from app.domains.signals.repository import SignalRepository
from app.domains.signals.schema import SignalCreate, SignalResponse
from app.domains.signals.types import SignalType


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
        total_cost_value, position_weights = self._calculate_weights(
            positions,
            portfolio.concentration_threshold,
        )
        return PortfolioSummaryResponse(
            portfolio_id=portfolio.id,
            concentration_threshold=portfolio.concentration_threshold,
            total_cost_value=total_cost_value,
            positions=position_weights,
        )

    def _calculate_weights(
        self,
        positions: list[Position],
        threshold: Decimal,
    ) -> tuple[Decimal, list[PositionWeight]]:
        costs = [position.quantity * position.avg_buy_price for position in positions]
        total_cost_value = sum(costs, Decimal("0"))
        weights: list[PositionWeight] = []

        for position, cost_value in zip(positions, costs, strict=True):
            weight = Decimal("0") if total_cost_value == 0 else cost_value / total_cost_value
            weights.append(
                PositionWeight(
                    asset_id=position.asset_id,
                    quantity=position.quantity,
                    avg_buy_price=position.avg_buy_price,
                    cost_value=cost_value,
                    weight=weight,
                    exceeds_threshold=weight > threshold,
                )
            )

        return total_cost_value, weights

    def _score_from_weight(self, weight: Decimal) -> int:
        return max(0, min(100, int(weight * Decimal("100"))))
