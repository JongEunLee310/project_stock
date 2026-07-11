from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.pagination import PaginationParams
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.assets.repository import AssetRepository
from app.domains.assets.schema import (
    AssetCreate,
    AssetDetailResponse,
    AssetLookupResponse,
    AssetResponse,
)
from app.domains.assets.service import AssetService
from app.domains.benchmark.schema import (
    BenchmarkComparisonResponse,
    BenchmarkRange,
)
from app.domains.benchmark.service import BenchmarkService
from app.domains.catalysts.schema import CatalystTimelineResponse
from app.domains.catalysts.service import CatalystService
from app.domains.decision_checklist.schema import (
    BuyChecklistNoteUpdate,
    BuyChecklistResponse,
)
from app.domains.decision_checklist.service import DecisionChecklistService
from app.domains.earnings.schema import EarningsSummaryResponse
from app.domains.earnings.service import EarningsService
from app.domains.news.news_disclosure_service import NewsDisclosureService
from app.domains.news.schema import NewsDisclosureResponse
from app.domains.research_coverage.schema import ResearchCoverageResponse
from app.domains.research_coverage.service import ResearchCoverageService
from app.domains.research_summary.schema import ResearchSummaryResponse
from app.domains.research_summary.service import ResearchSummaryService
from app.domains.users.model import User
from app.domains.valuation.schema import ValuationMetricsResponse
from app.domains.valuation.service import ValuationService

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
    description="Return paginated assets, optionally filtered by active status and/or symbol.",
)
def list_assets(
    pagination: Annotated[PaginationParams, Depends()],
    is_active: bool | None = None,
    symbol: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[list[AssetResponse]]:
    service = AssetService(db)
    items = service.list(
        is_active=is_active,
        symbol=symbol,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = service.count(is_active=is_active, symbol=symbol)
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.get(
    "/lookup",
    response_model=ApiResponse[AssetLookupResponse],
    summary="Lookup assets",
    description="Return market-provider symbol matches and whether each asset is already registered.",
)
def lookup_assets(
    query: str = Query(min_length=1),
    market: str | None = None,
    db: Session = Depends(get_db),
) -> ApiResponse[AssetLookupResponse]:
    return success(AssetService(db).lookup(query=query, market=market))


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
    "/{asset_id}/research-coverage",
    response_model=ApiResponse[ResearchCoverageResponse],
    summary="Get asset research coverage",
    description="Return collection coverage and freshness derived from stored research data.",
)
def get_asset_research_coverage(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ResearchCoverageResponse]:
    return success(ResearchCoverageService(db).get_coverage(asset_id))


@router.get(
    "/{asset_id}/news-disclosure",
    response_model=ApiResponse[NewsDisclosureResponse],
    summary="Get asset news and disclosures",
    description="Return recent news and disclosures as separate metadata projections.",
)
def get_asset_news_disclosure(
    asset_id: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[NewsDisclosureResponse]:
    asset = AssetRepository(db).get_by_id(asset_id)
    if asset is None:
        raise AppException(
            status_code=404,
            detail="종목을 찾을 수 없습니다.",
            error_code=ErrorCode.ASSET_NOT_FOUND,
        )
    return success(
        NewsDisclosureService(db).get_news_and_disclosures(
            asset_id=asset.id,
            symbol=asset.symbol,
            limit=limit,
        )
    )


@router.get(
    "/{asset_id}/catalysts",
    response_model=ApiResponse[CatalystTimelineResponse],
    summary="Get asset catalyst timeline",
    description="Return deterministic mock upcoming catalyst events for an asset.",
)
def get_asset_catalysts(
    asset_id: int,
    limit: Annotated[int, Query(ge=1, le=100)] = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[CatalystTimelineResponse]:
    return success(CatalystService(db).get_timeline(asset_id, limit))


@router.get(
    "/{asset_id}/valuation-metrics",
    response_model=ApiResponse[ValuationMetricsResponse],
    summary="Get asset valuation metrics",
    description="Return deterministic mock valuation metrics for an asset.",
)
def get_asset_valuation_metrics(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[ValuationMetricsResponse]:
    return success(ValuationService(db).get_metrics(asset_id))


@router.get(
    "/{asset_id}/earnings-summary",
    response_model=ApiResponse[EarningsSummaryResponse],
    summary="Get asset earnings summary",
    description="Return a deterministic mock quarterly earnings summary for an asset.",
)
def get_asset_earnings_summary(
    asset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[EarningsSummaryResponse]:
    return success(EarningsService(db).get_summary(asset_id))


@router.get(
    "/{asset_id}/benchmark-comparison",
    response_model=ApiResponse[BenchmarkComparisonResponse],
    summary="Get asset benchmark comparison",
    description="Return deterministic mock normalized asset and benchmark series.",
)
def get_asset_benchmark_comparison(
    asset_id: int,
    range_: Annotated[BenchmarkRange, Query(alias="range")] = (
        BenchmarkRange.THREE_MONTHS
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[BenchmarkComparisonResponse]:
    return success(BenchmarkService(db).get_comparison(asset_id, range_))


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
