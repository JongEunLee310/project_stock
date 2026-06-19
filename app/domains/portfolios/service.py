from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.assets.repository import AssetRepository
from app.domains.portfolios.model import Portfolio
from app.domains.portfolios.repository import PortfolioRepository, PositionRepository
from app.domains.portfolios.schema import (
    PortfolioCreate,
    PortfolioResponse,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)


class PortfolioService:
    def __init__(self, db: Session) -> None:
        self.asset_repo = AssetRepository(db)
        self.portfolio_repo = PortfolioRepository(db)
        self.position_repo = PositionRepository(db)

    def create_portfolio(
        self, user_id: int, data: PortfolioCreate
    ) -> PortfolioResponse:
        portfolio = self.portfolio_repo.create(user_id=user_id, name=data.name)
        return PortfolioResponse.model_validate(portfolio)

    def list_portfolios(self, user_id: int) -> list[PortfolioResponse]:
        return [
            PortfolioResponse.model_validate(portfolio)
            for portfolio in self.portfolio_repo.list_by_user(user_id)
        ]

    def add_position(
        self, portfolio_id: int, user_id: int, data: PositionCreate
    ) -> PositionResponse:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        if self.asset_repo.get_by_id(data.asset_id) is None:
            raise AppException(status_code=404, detail="종목을 찾을 수 없습니다.")
        if self.position_repo.get_by_portfolio_asset(portfolio.id, data.asset_id):
            raise AppException(
                status_code=400, detail="이미 포트폴리오에 추가된 종목입니다."
            )
        try:
            position = self.position_repo.create(portfolio.id, data)
        except IntegrityError as exc:
            raise AppException(
                status_code=400, detail="이미 포트폴리오에 추가된 종목입니다."
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
            raise AppException(status_code=404, detail="보유 종목을 찾을 수 없습니다.")
        updated_position = self.position_repo.update(position, data)
        return PositionResponse.model_validate(updated_position)

    def remove_position(
        self, portfolio_id: int, position_id: int, user_id: int
    ) -> None:
        portfolio = self._get_owned_portfolio(portfolio_id, user_id)
        position = self.position_repo.get_by_id(position_id)
        if position is None or position.portfolio_id != portfolio.id:
            raise AppException(status_code=404, detail="보유 종목을 찾을 수 없습니다.")
        self.position_repo.delete(position_id)

    def _get_owned_portfolio(self, portfolio_id: int, user_id: int) -> Portfolio:
        portfolio = self.portfolio_repo.get_by_id(portfolio_id)
        if portfolio is None:
            raise AppException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")
        if portfolio.user_id != user_id:
            raise AppException(status_code=403, detail="포트폴리오 접근 권한이 없습니다.")
        return portfolio
