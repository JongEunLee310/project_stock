from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.assets.schema import AssetCreate, AssetResponse
from app.domains.assets.service import AssetService

router = APIRouter()


@router.post("", response_model=ApiResponse[AssetResponse], status_code=201)
def register_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetResponse]:
    return success(AssetService(db).register(data))


@router.get("", response_model=ApiResponse[list[AssetResponse]])
def list_assets(
    is_active: bool | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AssetResponse]]:
    service = AssetService(db)
    items = service.list(is_active=is_active, offset=(page - 1) * size, limit=size)
    total = service.count(is_active=is_active)
    return paginated(items, page=page, size=size, total=total)


@router.get("/{asset_id}", response_model=ApiResponse[AssetResponse])
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> ApiResponse[AssetResponse]:
    return success(AssetService(db).get(asset_id))
