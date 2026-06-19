from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.theses.schema import ThesisCreate, ThesisResponse, ThesisUpdate
from app.domains.theses.service import ThesisService
from app.domains.users.model import User

router = APIRouter()


@router.post("", response_model=ApiResponse[ThesisResponse], status_code=201)
def create_thesis(
    data: ThesisCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ThesisResponse]:
    return success(ThesisService(db).create(current_user.id, data))


@router.put("/{thesis_id}", response_model=ApiResponse[ThesisResponse])
def update_thesis(
    thesis_id: int,
    data: ThesisUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ThesisResponse]:
    return success(ThesisService(db).update(thesis_id, current_user.id, data))


@router.get("/latest", response_model=ApiResponse[ThesisResponse])
def get_latest_thesis(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ThesisResponse]:
    return success(ThesisService(db).get_latest(asset_id, current_user.id))


@router.patch("/{thesis_id}/deactivate", response_model=ApiResponse[ThesisResponse])
def deactivate_thesis(
    thesis_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ThesisResponse]:
    return success(ThesisService(db).deactivate(thesis_id, current_user.id))
