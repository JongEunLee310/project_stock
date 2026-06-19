from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.portfolios.schema import (
    PortfolioCheckResponse,
    PortfolioCreate,
    PortfolioResponse,
    PortfolioSummaryResponse,
    PositionCreate,
    PositionResponse,
    PositionUpdate,
)
from app.domains.portfolios.service import PortfolioService
from app.domains.users.model import User

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[PortfolioResponse],
    status_code=201,
    summary="Create portfolio",
    description="Create a portfolio with a concentration threshold for the authenticated user.",
)
def create_portfolio(
    data: PortfolioCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PortfolioResponse]:
    return success(PortfolioService(db).create_portfolio(current_user.id, data))


@router.get(
    "",
    response_model=ApiResponse[list[PortfolioResponse]],
    summary="List portfolios",
    description="Return paginated portfolios for the authenticated user.",
)
def list_portfolios(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[PortfolioResponse]]:
    service = PortfolioService(db)
    items = service.list_portfolios(
        current_user.id,
        offset=(page - 1) * size,
        limit=size,
    )
    total = service.count_portfolios(current_user.id)
    return paginated(items, page=page, size=size, total=total)


@router.get(
    "/{portfolio_id}/summary",
    response_model=ApiResponse[PortfolioSummaryResponse],
    summary="Get portfolio summary",
    description="Return cost-value weights and concentration threshold status for a portfolio.",
)
def get_portfolio_summary(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PortfolioSummaryResponse]:
    return success(PortfolioService(db).get_summary(portfolio_id, current_user.id))


@router.post(
    "/{portfolio_id}/check",
    response_model=ApiResponse[PortfolioCheckResponse],
    summary="Check portfolio concentration",
    description="Evaluate portfolio concentration and return any created concentration signals.",
)
def check_portfolio_concentration(
    portfolio_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PortfolioCheckResponse]:
    return success(PortfolioService(db).check_concentration(portfolio_id, current_user.id))


@router.post(
    "/{portfolio_id}/positions",
    response_model=ApiResponse[PositionResponse],
    status_code=201,
    summary="Add portfolio position",
    description="Add an asset position to a portfolio owned by the authenticated user.",
)
def add_position(
    portfolio_id: int,
    data: PositionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PositionResponse]:
    return success(PortfolioService(db).add_position(portfolio_id, current_user.id, data))


@router.patch(
    "/{portfolio_id}/positions/{position_id}",
    response_model=ApiResponse[PositionResponse],
    summary="Update portfolio position",
    description="Update quantity and/or average buy price for a portfolio position.",
)
def update_position(
    portfolio_id: int,
    position_id: int,
    data: PositionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[PositionResponse]:
    return success(
        PortfolioService(db).update_position(
            portfolio_id,
            position_id,
            current_user.id,
            data,
        )
    )


@router.delete(
    "/{portfolio_id}/positions/{position_id}",
    response_model=ApiResponse[None],
    summary="Remove portfolio position",
    description="Remove a position from a portfolio owned by the authenticated user.",
)
def remove_position(
    portfolio_id: int,
    position_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    PortfolioService(db).remove_position(portfolio_id, position_id, current_user.id)
    return success(None)
