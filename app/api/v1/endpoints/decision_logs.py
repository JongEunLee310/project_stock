from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.decision_logs.schema import (
    DecisionLogCreate,
    DecisionLogResponse,
    DecisionLogUpdate,
)
from app.domains.decision_logs.service import DecisionLogService
from app.domains.users.model import User

router = APIRouter()
decision_log_sort = sort_param(
    allowed_fields={"decided_at", "created_at"},
    default="-decided_at",
)


@router.get(
    "",
    response_model=ApiResponse[list[DecisionLogResponse]],
    summary="List decision logs",
    description="Return paginated decision logs for the authenticated user.",
)
def list_decision_logs(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(decision_log_sort)],
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[DecisionLogResponse]]:
    service = DecisionLogService(db)
    items = service.list_decision_logs(
        current_user.id,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort.value,
    )
    total = service.count_decision_logs(current_user.id)
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
    return success(DecisionLogService(db).create_decision_log(current_user.id, data))


@router.get(
    "/{decision_log_id}",
    response_model=ApiResponse[DecisionLogResponse],
    summary="Get decision log",
    description="Return one decision log owned by the authenticated user.",
)
def get_decision_log(
    decision_log_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[DecisionLogResponse]:
    return success(
        DecisionLogService(db).get_decision_log(decision_log_id, current_user.id),
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
        DecisionLogService(db).update_decision_log(
            decision_log_id,
            current_user.id,
            data,
        ),
    )
