from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.users.model import User
from app.domains.watchlists.schema import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistItemSort,
    WatchlistResponse,
)
from app.domains.watchlists.service import WatchlistService

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[WatchlistResponse],
    status_code=201,
    summary="Create watchlist",
    description="Create a watchlist owned by the authenticated user.",
)
def create_watchlist(
    data: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistResponse]:
    return success(WatchlistService(db).create_watchlist(current_user.id, data))


@router.get(
    "",
    response_model=ApiResponse[list[WatchlistResponse]],
    summary="List watchlists",
    description="Return paginated watchlists for the authenticated user.",
)
def list_watchlists(
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[WatchlistResponse]]:
    service = WatchlistService(db)
    items = service.list_watchlists(
        current_user.id,
        offset=(page - 1) * size,
        limit=size,
    )
    total = service.count_watchlists(current_user.id)
    return paginated(items, page=page, size=size, total=total)


@router.get(
    "/{watchlist_id}/items",
    response_model=ApiResponse[list[WatchlistItemResponse]],
    summary="List watchlist items",
    description="Return paginated items for a watchlist owned by the authenticated user.",
)
def list_watchlist_items(
    watchlist_id: int,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    sort: WatchlistItemSort = "priority",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[WatchlistItemResponse]]:
    service = WatchlistService(db)
    items = service.list_items(
        watchlist_id,
        current_user.id,
        offset=(page - 1) * size,
        limit=size,
        sort=sort,
    )
    total = service.count_items(watchlist_id, current_user.id)
    return paginated(items, page=page, size=size, total=total)


@router.post(
    "/{watchlist_id}/items",
    response_model=ApiResponse[WatchlistItemResponse],
    status_code=201,
    summary="Add watchlist item",
    description="Add an asset to a watchlist owned by the authenticated user.",
)
def add_watchlist_item(
    watchlist_id: int,
    data: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistItemResponse]:
    return success(WatchlistService(db).add_item(watchlist_id, current_user.id, data))


@router.delete(
    "/{watchlist_id}/items/{item_id}",
    response_model=ApiResponse[None],
    summary="Remove watchlist item",
    description="Remove an item from a watchlist owned by the authenticated user.",
)
def remove_watchlist_item(
    watchlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    WatchlistService(db).remove_item(watchlist_id, item_id, current_user.id)
    return success(None)
