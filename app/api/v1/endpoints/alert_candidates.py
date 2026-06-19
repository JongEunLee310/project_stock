from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alert_candidates.schema import AlertCandidateResponse
from app.domains.alert_candidates.service import AlertCandidateService
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[AlertCandidateResponse]],
    summary="List alert candidates",
    description=(
        "Return paginated alert candidates for the authenticated user with optional "
        "filters."
    ),
)
def list_alert_candidates(
    candidate_type: AlertCandidateType | None = None,
    importance: AlertImportance | None = None,
    status: AlertCandidateStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertCandidateResponse]]:
    candidate_type_value = (
        candidate_type.value if candidate_type is not None else None
    )
    importance_value = importance.value if importance is not None else None
    status_value = status.value if status is not None else None
    service = AlertCandidateService(db)
    items = [
        AlertCandidateResponse.model_validate(candidate)
        for candidate in service.list_candidates(
            current_user.id,
            candidate_type=candidate_type_value,
            importance=importance_value,
            status=status_value,
            offset=(page - 1) * size,
            limit=size,
        )
    ]
    total = service.count_candidates(
        current_user.id,
        candidate_type=candidate_type_value,
        importance=importance_value,
        status=status_value,
    )
    return paginated(items, page=page, size=size, total=total)


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
