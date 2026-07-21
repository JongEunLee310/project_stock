from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.adapters.factory import get_llm_gateway
from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.decision_logs.schema import (
    DecisionActivateRequest,
    DecisionAssistRequest,
    DecisionAssistResponse,
    DecisionLogCreate,
    DecisionLogDetailResponse,
    DecisionLogListItem,
    DecisionOverviewResponse,
    DecisionReviewCreate,
    DecisionReviewResponse,
    DecisionLogResponse,
    DecisionLogUpdate,
)
from app.domains.decision_logs.assist_service import DecisionAssistService
from app.domains.decision_logs.service import DecisionLogService
from app.domains.decision_logs.types import DecisionStatus, DecisionType, TargetType
from app.domains.users.model import User

router = APIRouter()
decision_log_sort = sort_param(
    allowed_fields={"decided_at", "created_at"},
    default="-created_at",
)


@router.get(
    "",
    response_model=ApiResponse[list[DecisionLogListItem]],
    summary="List decision logs",
    description="Return paginated decision logs for the authenticated user.",
)
def list_decision_logs(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(decision_log_sort)],
    target_type: TargetType | None = None,
    symbol: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
    decision_type: DecisionType | None = None,
    status: DecisionStatus | None = None,
    risk_type: Annotated[str | None, Query(min_length=1, max_length=40)] = None,
    review_due_before: datetime | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[DecisionLogListItem]]:
    service = DecisionLogService(db)
    items, total = service.list_decision_logs(
        current_user.id,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort.value,
        target_type=target_type,
        symbol=symbol,
        decision_type=decision_type,
        status=status,
        risk_type=risk_type,
        review_due_before=review_due_before,
    )
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "",
    response_model=ApiResponse[DecisionLogResponse],
    status_code=201,
    summary="Create decision log",
    description="Create a decision log owned by the authenticated user.",
)
def create_decision_log(
    data: DecisionLogCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogResponse]:
    return success(DecisionLogService(db).create_decision(current_user.id, data))


@router.get(
    "/overview",
    response_model=ApiResponse[DecisionOverviewResponse],
    summary="Get decision log overview",
    description="Return decision activity aggregates for the authenticated user.",
)
def get_decision_log_overview(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionOverviewResponse]:
    return success(DecisionLogService(db).get_overview(current_user.id))


@router.get(
    "/review-queue",
    response_model=ApiResponse[list[DecisionLogListItem]],
    summary="List decision logs due for review",
    description="Return due DATE reviews for the authenticated user.",
)
def get_decision_log_review_queue(
    pagination: Annotated[PaginationParams, Depends()],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[DecisionLogListItem]]:
    items, total = DecisionLogService(db).get_review_queue(
        current_user.id,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "/assist",
    response_model=ApiResponse[DecisionAssistResponse],
    summary="Assist decision draft",
    description=(
        "Return non-persistent AI suggestions for an authenticated user's "
        "decision draft."
    ),
)
def assist_decision_log(
    data: DecisionAssistRequest,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionAssistResponse]:
    return success(
        DecisionAssistService(get_llm_gateway()).assist(current_user.id, data)
    )


@router.post(
    "/{decision_log_id}/reviews",
    response_model=ApiResponse[DecisionReviewResponse],
    status_code=201,
    summary="Create decision review",
    description="Create a retrospective review for an owned decision log.",
)
def create_decision_review(
    decision_log_id: int,
    data: DecisionReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionReviewResponse]:
    return success(
        DecisionLogService(db).create_review(
            decision_log_id,
            current_user.id,
            data,
        )
    )


@router.get(
    "/{decision_log_id}/reviews",
    response_model=ApiResponse[list[DecisionReviewResponse]],
    summary="List decision reviews",
    description="Return newest-first retrospective reviews for an owned decision log.",
)
def list_decision_reviews(
    decision_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[DecisionReviewResponse]]:
    return success(
        DecisionLogService(db).list_reviews(decision_log_id, current_user.id)
    )


@router.get(
    "/{decision_log_id}/similar",
    response_model=ApiResponse[list[DecisionLogListItem]],
    summary="List similar decision logs",
    description="Return the most similar decision logs owned by the user.",
)
def list_similar_decision_logs(
    decision_log_id: int,
    limit: Annotated[int, Query(ge=1, le=20)] = 5,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[DecisionLogListItem]]:
    return success(
        DecisionLogService(db).list_similar(
            decision_log_id,
            current_user.id,
            limit,
        )
    )


@router.get(
    "/{decision_log_id}",
    response_model=ApiResponse[DecisionLogDetailResponse],
    summary="Get decision log",
    description="Return one decision log owned by the authenticated user.",
)
def get_decision_log(
    decision_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogDetailResponse]:
    return success(
        DecisionLogService(db).get_decision(decision_log_id, current_user.id),
    )


@router.patch(
    "/{decision_log_id}",
    response_model=ApiResponse[DecisionLogResponse],
    summary="Update decision log",
    description="Update mutable fields for a decision log owned by the user.",
)
def update_decision_log(
    decision_log_id: int,
    data: DecisionLogUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogResponse]:
    return success(
        DecisionLogService(db).update_draft(
            decision_log_id,
            current_user.id,
            data,
        ),
    )


@router.post(
    "/{decision_log_id}/activate",
    response_model=ApiResponse[DecisionLogResponse],
    summary="Activate decision log",
    description="Activate a draft decision log and preserve supplied snapshots.",
)
def activate_decision_log(
    decision_log_id: int,
    data: DecisionActivateRequest | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogResponse]:
    return success(
        DecisionLogService(db).activate(
            decision_log_id,
            current_user.id,
            data or DecisionActivateRequest(),
        )
    )


@router.post(
    "/{decision_log_id}/revise",
    response_model=ApiResponse[DecisionLogDetailResponse],
    summary="Revise decision log",
    description="Create a new draft that supersedes an owned decision log.",
)
def revise_decision_log(
    decision_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogDetailResponse]:
    return success(
        DecisionLogService(db).revise(decision_log_id, current_user.id)
    )
