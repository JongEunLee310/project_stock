from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.domains.users.model import User
from app.domains.watchlists.schema import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemResponse,
    WatchlistResponse,
)
from app.domains.watchlists.service import WatchlistService

router = APIRouter()


@router.post("", response_model=WatchlistResponse, status_code=201)
def create_watchlist(
    data: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistResponse:
    return WatchlistService(db).create_watchlist(current_user.id, data)


@router.get("", response_model=list[WatchlistResponse])
def list_watchlists(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[WatchlistResponse]:
    return WatchlistService(db).list_watchlists(current_user.id)


@router.post("/{watchlist_id}/items", response_model=WatchlistItemResponse, status_code=201)
def add_watchlist_item(
    watchlist_id: int,
    data: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WatchlistItemResponse:
    return WatchlistService(db).add_item(watchlist_id, current_user.id, data)


@router.delete("/{watchlist_id}/items/{item_id}", status_code=204)
def remove_watchlist_item(
    watchlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    WatchlistService(db).remove_item(watchlist_id, item_id, current_user.id)
    return Response(status_code=204)
