from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.portfolios.model import Portfolio, Position
from app.domains.portfolios.schema import PortfolioCreate, PositionCreate, PositionUpdate


class PortfolioRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, portfolio_id: int) -> Portfolio | None:
        return self.db.get(Portfolio, portfolio_id)

    def list_by_user(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Portfolio]:
        stmt = select(Portfolio).where(Portfolio.user_id == user_id).order_by(Portfolio.id)
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(self, user_id: int) -> int:
        stmt = select(func.count()).select_from(Portfolio).where(Portfolio.user_id == user_id)
        return int(self.db.scalar(stmt) or 0)

    def create(self, user_id: int, data: PortfolioCreate) -> Portfolio:
        portfolio = Portfolio(
            user_id=user_id,
            name=data.name,
            concentration_threshold=data.concentration_threshold,
            cash_balance=data.cash_balance,
        )
        self.db.add(portfolio)
        self.db.commit()
        self.db.refresh(portfolio)
        return portfolio


class PositionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, position_id: int) -> Position | None:
        return self.db.get(Position, position_id)

    def get_by_portfolio_asset(self, portfolio_id: int, asset_id: int) -> Position | None:
        stmt = select(Position).where(
            Position.portfolio_id == portfolio_id,
            Position.asset_id == asset_id,
        )
        return self.db.scalars(stmt).first()

    def list_by_portfolio(self, portfolio_id: int) -> list[Position]:
        stmt = (
            select(Position)
            .where(Position.portfolio_id == portfolio_id)
            .order_by(Position.id)
        )
        return list(self.db.scalars(stmt).all())

    def create(self, portfolio_id: int, data: PositionCreate) -> Position:
        position = Position(
            portfolio_id=portfolio_id,
            asset_id=data.asset_id,
            quantity=data.quantity,
            avg_buy_price=data.avg_buy_price,
        )
        self.db.add(position)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            raise
        self.db.refresh(position)
        return position

    def update(self, position: Position, data: PositionUpdate) -> Position:
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(position, field, value)
        self.db.commit()
        self.db.refresh(position)
        return position

    def delete(self, position_id: int) -> None:
        position = self.get_by_id(position_id)
        if position is None:
            return
        self.db.delete(position)
        self.db.commit()
