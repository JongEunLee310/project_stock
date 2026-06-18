from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domains.assets.schema import AssetCreate, AssetResponse
from app.domains.assets.service import AssetService

router = APIRouter()


@router.post("", response_model=AssetResponse, status_code=201)
def register_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
) -> AssetResponse:
    return AssetService(db).register(data)


@router.get("", response_model=list[AssetResponse])
def list_assets(
    is_active: bool | None = None,
    db: Session = Depends(get_db),
) -> list[AssetResponse]:
    return AssetService(db).list(is_active=is_active)


@router.get("/{asset_id}", response_model=AssetResponse)
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> AssetResponse:
    return AssetService(db).get(asset_id)
