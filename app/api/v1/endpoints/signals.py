from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi import Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.signals.schema import SignalCreate, SignalResponse
from app.domains.signals.service import SignalService
from app.domains.users.model import User

router = APIRouter()


@router.post("", response_model=ApiResponse[SignalResponse], status_code=201)
def create_signal(
    data: SignalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SignalResponse]:
    return success(SignalResponse.model_validate(SignalService(db).create_signal(data)))


@router.get("", response_model=ApiResponse[list[SignalResponse]])
def list_signals(
    asset_id: int,
    include_expired: bool = False,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[SignalResponse]]:
    service = SignalService(db)
    items = [
        SignalResponse.model_validate(signal)
        for signal in service.list_signals(
            asset_id,
            include_expired,
            offset=(page - 1) * size,
            limit=size,
        )
    ]
    total = service.count_signals(asset_id, include_expired)
    return paginated(items, page=page, size=size, total=total)


@router.get("/{signal_id}", response_model=ApiResponse[SignalResponse])
def get_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[SignalResponse]:
    return success(SignalResponse.model_validate(SignalService(db).get_signal(signal_id)))
