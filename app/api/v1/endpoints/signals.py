from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.signals.schema import (
    SignalCreate,
    SignalChangeTimelineItem,
    SignalExpandedResponse,
    SignalSummary,
    SignalResponse,
)
from app.domains.signals.service import SignalService
from app.domains.users.model import User

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[SignalResponse],
    status_code=201,
    summary="Create signal",
    description="Create an investment signal for an asset, optionally linked to a thesis or news item.",
)
def create_signal(
    data: SignalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SignalResponse]:
    return success(SignalResponse.model_validate(SignalService(db).create_signal(data)))


@router.get(
    "",
    response_model=ApiResponse[list[Any]],
    summary="List signals",
    description=(
        "Return paginated signals for an asset, with optional expired-signal inclusion. "
        "Pass view=current to return one active dominant signal per asset; include_expired is ignored for current. "
        "Pass expand=asset to include asset quote information in each item."
    ),
)
def list_signals(
    pagination: Annotated[PaginationParams, Depends()],
    asset_id: int | None = None,
    include_expired: bool = False,
    expand: str | None = Query(
        default=None,
        description="Comma-separated expand fields. Supported: asset",
    ),
    view: str = Query(default="all"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    service = SignalService(db)
    expanded_items: list[SignalExpandedResponse]
    plain_items: list[Any]
    if expand is not None and "asset" in [e.strip() for e in expand.split(",")]:
        expanded_items = service.list_signals_expanded(
            asset_id,
            include_expired,
            offset=pagination.offset,
            limit=pagination.limit,
            view=view,
        )
        total = service.count_signals(asset_id, include_expired, view=view)
        return paginated(
            expanded_items,
            page=pagination.page,
            size=pagination.size,
            total=total,
        )
    if view == "current":
        plain_items = service.list_current_signals(
            asset_id,
            offset=pagination.offset,
            limit=pagination.limit,
        )
        total = service.count_signals(asset_id, include_expired, view=view)
        return paginated(
            plain_items,
            page=pagination.page,
            size=pagination.size,
            total=total,
        )
    plain_items = [
        SignalResponse.model_validate(signal)
        for signal in service.list_signals(
            asset_id,
            include_expired,
            offset=pagination.offset,
            limit=pagination.limit,
            view=view,
        )
    ]
    total = service.count_signals(asset_id, include_expired, view=view)
    return paginated(
        plain_items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.get(
    "/changes",
    response_model=ApiResponse[list[SignalChangeTimelineItem]],
    summary="List signal changes",
    description="Return recent asset dominant-signal changes derived from daily snapshots.",
)
def list_signal_changes(
    limit: int = Query(default=20, ge=1, le=100),
    since: date | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[SignalChangeTimelineItem]]:
    return success(SignalService(db).list_recent_changes(limit=limit, since=since))


@router.get(
    "/summary",
    response_model=ApiResponse[SignalSummary],
    summary="Get signal summary",
    description="Return current dominant-signal category counts and snapshot deltas.",
)
def get_signal_summary(
    view: str = Query(default="current"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SignalSummary]:
    return success(SignalService(db).summary(view=view))


@router.get(
    "/{signal_id}",
    response_model=ApiResponse[SignalResponse],
    summary="Get signal",
    description="Return a single signal by id.",
)
def get_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SignalResponse]:
    return success(SignalResponse.model_validate(SignalService(db).get_signal(signal_id)))
