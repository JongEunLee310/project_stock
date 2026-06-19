from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.domains.signals.schema import SignalCreate, SignalResponse
from app.domains.signals.service import SignalService
from app.domains.users.model import User

router = APIRouter()


@router.post("", response_model=SignalResponse, status_code=201)
def create_signal(
    data: SignalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    return SignalResponse.model_validate(SignalService(db).create_signal(data))


@router.get("", response_model=list[SignalResponse])
def list_signals(
    asset_id: int,
    include_expired: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[SignalResponse]:
    return [
        SignalResponse.model_validate(signal)
        for signal in SignalService(db).list_signals(asset_id, include_expired)
    ]


@router.get("/{signal_id}", response_model=SignalResponse)
def get_signal(
    signal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SignalResponse:
    return SignalResponse.model_validate(SignalService(db).get_signal(signal_id))
