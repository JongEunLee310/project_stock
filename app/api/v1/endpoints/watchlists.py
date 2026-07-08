from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.adapters.factory import get_llm_gateway
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.users.model import User
from app.domains.watchlists.evaluations_service import WatchlistEvaluationsService
from app.domains.watchlists.observations_service import WatchlistObservationsService
from app.domains.watchlists.recommendations_service import (
    WatchlistRecommendationsService,
)
from app.domains.watchlists.schema import (
    WatchlistCreate,
    WatchlistItemCreate,
    WatchlistItemExpandedResponse,
    WatchlistItemResponse,
    WatchlistEvaluationsResponse,
    WatchlistObservationsResponse,
    WatchlistRecommendationsResponse,
    WatchlistResponse,
    WatchlistSparklineResponse,
    WatchlistSummaryResponse,
    WatchlistSummaryTrendResponse,
)
from app.domains.watchlists.service import WatchlistService
from app.domains.watchlists.sparkline_service import WatchlistSparklineService
from app.domains.watchlists.trend_service import WatchlistSummaryTrendService

router = APIRouter()
watchlist_item_sort = sort_param(
    allowed_fields={"priority", "created_at"},
    default="priority",
)


@router.post(
    "",
    response_model=ApiResponse[WatchlistResponse],
    status_code=201,
    summary="Create watchlist",
    description="Create a watchlist owned by the authenticated user.",
)
def create_watchlist(
    data: WatchlistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistResponse]:
    return success(WatchlistService(db).create_watchlist(current_user.id, data))


@router.get(
    "",
    response_model=ApiResponse[list[WatchlistResponse]],
    summary="List watchlists",
    description="Return paginated watchlists for the authenticated user.",
)
def list_watchlists(
    pagination: Annotated[PaginationParams, Depends()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[WatchlistResponse]]:
    service = WatchlistService(db)
    items = service.list_watchlists(
        current_user.id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = service.count_watchlists(current_user.id)
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.get(
    "/{watchlist_id}/items",
    response_model=ApiResponse[list[Any]],
    summary="List watchlist items",
    description=(
        "Return paginated items for a watchlist owned by the authenticated user. "
        "Pass expand=asset to include asset quote information in each item."
    ),
)
def list_watchlist_items(
    watchlist_id: int,
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(watchlist_item_sort)],
    expand: str | None = Query(
        default=None,
        description="Comma-separated expand fields. Supported: asset",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    service = WatchlistService(db)
    expanded_items: list[WatchlistItemExpandedResponse]
    plain_items: list[WatchlistItemResponse]
    if expand is not None and "asset" in [e.strip() for e in expand.split(",")]:
        expanded_items = service.list_items_expanded(
            watchlist_id,
            current_user.id,
            offset=pagination.offset,
            limit=pagination.limit,
            sort=sort.value,
        )
        total = service.count_items(watchlist_id, current_user.id)
        return paginated(
            expanded_items,
            page=pagination.page,
            size=pagination.size,
            total=total,
        )
    plain_items = service.list_items(
        watchlist_id,
        current_user.id,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort.value,
    )
    total = service.count_items(watchlist_id, current_user.id)
    return paginated(
        plain_items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.get(
    "/{watchlist_id}/summary",
    response_model=ApiResponse[WatchlistSummaryResponse],
    summary="Get watchlist summary",
    description="Return calculated summary metrics for a watchlist owned by the authenticated user.",
)
def get_watchlist_summary(
    watchlist_id: int,
    recent_limit: int = Query(default=5, ge=0, le=50),
    portfolio_id: int | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistSummaryResponse]:
    return success(
        WatchlistService(db).get_summary(
            watchlist_id,
            current_user.id,
            portfolio_id=portfolio_id,
            recent_limit=recent_limit,
        )
    )


@router.get(
    "/{watchlist_id}/summary/trends",
    response_model=ApiResponse[WatchlistSummaryTrendResponse],
    summary="Get watchlist summary trend series",
    description="Return daily summary trend counts for a watchlist owned by the authenticated user.",
)
def get_watchlist_summary_trends(
    watchlist_id: int,
    days: Annotated[int, Query(ge=1, le=90)] = 14,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistSummaryTrendResponse]:
    return success(
        WatchlistSummaryTrendService(db).get_trends(
            watchlist_id,
            current_user.id,
            days,
        )
    )


@router.get(
    "/{watchlist_id}/sparklines",
    response_model=ApiResponse[WatchlistSparklineResponse],
    summary="Get watchlist sparkline series",
    description="Return daily close sparkline series for all assets in a watchlist.",
)
def get_watchlist_sparklines(
    watchlist_id: int,
    sparkline_range: Annotated[
        Literal["1M", "3M", "6M", "1Y"],
        Query(alias="range"),
    ] = "1M",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistSparklineResponse]:
    return success(
        WatchlistSparklineService(db).get_sparklines(
            watchlist_id,
            current_user.id,
            range_value=sparkline_range,
        )
    )


@router.get(
    "/{watchlist_id}/observations",
    response_model=ApiResponse[WatchlistObservationsResponse],
    summary="Generate watchlist observations",
    description="Generate AI observation notes for a watchlist owned by the authenticated user.",
)
def get_watchlist_observations(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistObservationsResponse]:
    return success(
        WatchlistObservationsService(db, get_llm_gateway()).generate(
            watchlist_id,
            current_user.id,
        )
    )


@router.get(
    "/{watchlist_id}/evaluations",
    response_model=ApiResponse[WatchlistEvaluationsResponse],
    summary="Generate watchlist evaluations",
    description="Generate AI evaluation badges for a watchlist owned by the authenticated user.",
)
def get_watchlist_evaluations(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistEvaluationsResponse]:
    return success(
        WatchlistEvaluationsService(db, get_llm_gateway()).generate(
            watchlist_id,
            current_user.id,
        )
    )


@router.get(
    "/{watchlist_id}/recommendations",
    response_model=ApiResponse[WatchlistRecommendationsResponse],
    summary="Generate watchlist recommendations",
    description="Generate AI stock recommendations for a watchlist owned by the authenticated user.",
)
def get_watchlist_recommendations(
    watchlist_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistRecommendationsResponse]:
    return success(
        WatchlistRecommendationsService(db, get_llm_gateway()).generate(
            watchlist_id,
            current_user.id,
        )
    )


@router.post(
    "/{watchlist_id}/items",
    response_model=ApiResponse[WatchlistItemResponse],
    status_code=201,
    summary="Add watchlist item",
    description="Add an asset to a watchlist owned by the authenticated user.",
)
def add_watchlist_item(
    watchlist_id: int,
    data: WatchlistItemCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[WatchlistItemResponse]:
    return success(WatchlistService(db).add_item(watchlist_id, current_user.id, data))


@router.delete(
    "/{watchlist_id}/items/{item_id}",
    response_model=ApiResponse[None],
    summary="Remove watchlist item",
    description="Remove an item from a watchlist owned by the authenticated user.",
)
def remove_watchlist_item(
    watchlist_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[None]:
    WatchlistService(db).remove_item(watchlist_id, item_id, current_user.id)
    return success(None)
