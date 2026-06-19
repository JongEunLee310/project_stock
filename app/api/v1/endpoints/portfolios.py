from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.domains.portfolios.schema import (
    PortfolioCreate,
    PortfolioResponse,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)
from app.domains.portfolios.service import PortfolioService
from app.domains.users.model import User

router = APIRouter()


@router.post("", response_model=PortfolioResponse, status_code=201)
def create_portfolio(
    data: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PortfolioResponse:
    return PortfolioService(db).create_portfolio(current_user.id, data)


@router.get("", response_model=list[PortfolioResponse])
def list_portfolios(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[PortfolioResponse]:
    return PortfolioService(db).list_portfolios(current_user.id)


@router.post("/{portfolio_id}/positions", response_model=PositionResponse, status_code=201)
def add_position(
    portfolio_id: int,
    data: PositionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PositionResponse:
    return PortfolioService(db).add_position(portfolio_id, current_user.id, data)


@router.patch("/{portfolio_id}/positions/{position_id}", response_model=PositionResponse)
def update_position(
    portfolio_id: int,
    position_id: int,
    data: PositionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> PositionResponse:
    return PortfolioService(db).update_position(
        portfolio_id,
        position_id,
        current_user.id,
        data,
    )


@router.delete("/{portfolio_id}/positions/{position_id}", status_code=204)
def remove_position(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    PortfolioService(db).remove_position(portfolio_id, position_id, current_user.id)
    return Response(status_code=204)
