from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alert_candidates.schema import (
    AlertCandidateExpandedResponse,
    AlertCandidateResponse,
)
from app.domains.alert_candidates.service import AlertCandidateService
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from app.domains.users.model import User

router = APIRouter()
alert_candidate_sort = sort_param(
    allowed_fields={"created_at", "id"},
    default="-created_at",
)


@router.get(
    "",
    response_model=ApiResponse[list[Any]],
    summary="List alert candidates",
    description=(
        "Return paginated alert candidates for the authenticated user with optional "
        "filters. Pass expand=asset to include asset quote information in each item."
    ),
)
def list_alert_candidates(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(alert_candidate_sort)],
    candidate_type: AlertCandidateType | None = None,
    importance: AlertImportance | None = None,
    status: AlertCandidateStatus | None = None,
    expand: str | None = Query(
        default=None,
        description="Comma-separated expand fields. Supported: asset",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    candidate_type_value = (
        candidate_type.value if candidate_type is not None else None
    )
    importance_value = importance.value if importance is not None else None
    status_value = status.value if status is not None else None
    service = AlertCandidateService(db)
    expanded_items: list[AlertCandidateExpandedResponse]
    plain_items: list[AlertCandidateResponse]
    if expand is not None and "asset" in [e.strip() for e in expand.split(",")]:
        expanded_items = service.list_candidates_expanded(
            current_user.id,
            candidate_type=candidate_type_value,
            importance=importance_value,
            status=status_value,
            offset=pagination.offset,
            limit=pagination.limit,
            sort=sort.value,
        )
        total = service.count_candidates(
            current_user.id,
            candidate_type=candidate_type_value,
            importance=importance_value,
            status=status_value,
        )
        return paginated(
            expanded_items,
            page=pagination.page,
            size=pagination.size,
            total=total,
        )
    items = [
        AlertCandidateResponse.model_validate(candidate)
        for candidate in service.list_candidates(
            current_user.id,
            candidate_type=candidate_type_value,
            importance=importance_value,
            status=status_value,
            offset=pagination.offset,
            limit=pagination.limit,
            sort=sort.value,
        )
    ]
    plain_items = items
    total = service.count_candidates(
        current_user.id,
        candidate_type=candidate_type_value,
        importance=importance_value,
        status=status_value,
    )
    return paginated(
        plain_items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "/{candidate_id}/read",
    response_model=ApiResponse[AlertCandidateResponse],
    summary="Mark alert candidate read",
    description="Mark an alert candidate as read for the authenticated user.",
)
def mark_alert_candidate_read(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertCandidateResponse]:
    return success(
        AlertCandidateResponse.model_validate(
            AlertCandidateService(db).mark_read(candidate_id, current_user.id)
        )
    )


@router.post(
    "/{candidate_id}/confirm",
    response_model=ApiResponse[AlertCandidateResponse],
    summary="Confirm alert candidate",
    description="Confirm an alert candidate for the authenticated user.",
)
def confirm_alert_candidate(
    candidate_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertCandidateResponse]:
    return success(
        AlertCandidateResponse.model_validate(
            AlertCandidateService(db).confirm(candidate_id, current_user.id)
        )
    )
