from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.signals.schema import (
    SignalCreate,
    SignalExpandedResponse,
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
        "Pass expand=asset to include asset quote information in each item."
    ),
)
def list_signals(
    asset_id: int,
    pagination: Annotated[PaginationParams, Depends()],
    include_expired: bool = False,
    expand: str | None = Query(
        default=None,
        description="Comma-separated expand fields. Supported: asset",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    service = SignalService(db)
    expanded_items: list[SignalExpandedResponse]
    plain_items: list[SignalResponse]
    if expand is not None and "asset" in [e.strip() for e in expand.split(",")]:
        expanded_items = service.list_signals_expanded(
            asset_id,
            include_expired,
            offset=pagination.offset,
            limit=pagination.limit,
        )
        total = service.count_signals(asset_id, include_expired)
        return paginated(
            expanded_items,
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
        )
    ]
    total = service.count_signals(asset_id, include_expired)
    return paginated(
        plain_items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


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
