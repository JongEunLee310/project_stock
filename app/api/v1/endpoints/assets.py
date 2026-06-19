from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.assets.schema import AssetCreate, AssetDetailResponse, AssetResponse
from app.domains.assets.service import AssetService
from app.domains.decision_checklist.schema import (
    BuyChecklistNoteUpdate,
    BuyChecklistResponse,
)
from app.domains.decision_checklist.service import DecisionChecklistService
from app.domains.research_summary.schema import ResearchSummaryResponse
from app.domains.research_summary.service import ResearchSummaryService
from app.domains.users.model import User

router = APIRouter()


@router.post(
    "",
    response_model=ApiResponse[AssetResponse],
    status_code=201,
    summary="Register asset",
    description="Create an investable asset that can be referenced by watchlists, theses, reports, and signals.",
)
def register_asset(
    data: AssetCreate,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetResponse]:
    return success(AssetService(db).register(data))


@router.get(
    "",
    response_model=ApiResponse[list[AssetResponse]],
    summary="List assets",
    description="Return paginated assets, optionally filtered by active status.",
)
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


@router.get(
    "/{asset_id}/detail",
    response_model=ApiResponse[AssetDetailResponse],
    summary="Get asset detail",
    description="Return basic asset information with deterministic mock market quote data.",
)
def get_asset_detail(
    asset_id: int,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetDetailResponse]:
    return success(AssetService(db).get_detail(asset_id))


@router.get(
    "/{asset_id}/research-summary",
    response_model=ApiResponse[ResearchSummaryResponse],
    summary="Get asset research summary",
    description="Return a deterministic mock research summary for an asset.",
)
def get_asset_research_summary(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ResearchSummaryResponse]:
    return success(ResearchSummaryService(db).get_summary(asset_id))


@router.get(
    "/{asset_id}/buy-checklist",
    response_model=ApiResponse[BuyChecklistResponse],
    summary="Get buy checklist",
    description="Return a rule-based pre-buy checklist and the authenticated user's note.",
)
def get_buy_checklist(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[BuyChecklistResponse]:
    return success(DecisionChecklistService(db).get_checklist(asset_id, current_user.id))


@router.put(
    "/{asset_id}/buy-checklist",
    response_model=ApiResponse[BuyChecklistResponse],
    summary="Save buy checklist note",
    description="Save the authenticated user's judgment memo and checked checklist items.",
)
def save_buy_checklist_note(
    asset_id: int,
    data: BuyChecklistNoteUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[BuyChecklistResponse]:
    return success(
        DecisionChecklistService(db).save_note(asset_id, current_user.id, data)
    )


@router.get(
    "/{asset_id}",
    response_model=ApiResponse[AssetResponse],
    summary="Get asset",
    description="Return a single asset by id.",
)
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> ApiResponse[AssetResponse]:
    return success(AssetService(db).get(asset_id))
