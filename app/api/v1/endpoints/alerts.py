from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alerts.schema import AlertResponse
from app.domains.alerts.service import AlertService
from app.domains.alerts.types import AlertStatus
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[AlertResponse]],
    summary="List alerts",
    description="Return paginated alerts for the authenticated user, optionally filtered by status.",
)
def list_alerts(
    pagination: Annotated[PaginationParams, Depends()],
    status: AlertStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertResponse]]:
    status_value = status.value if status is not None else None
    service = AlertService(db)
    items = service.list_alert_responses(
        current_user.id,
        status_value,
        offset=pagination.offset,
        limit=pagination.limit,
    )
    total = service.count_alerts(current_user.id, status_value)
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "/{alert_id}/read",
    response_model=ApiResponse[AlertResponse],
    summary="Mark alert read",
    description="Mark an alert as read for the authenticated user.",
)
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertResponse]:
    return success(AlertService(db).mark_read_response(alert_id, current_user.id))


@router.post(
    "/{alert_id}/dismiss",
    response_model=ApiResponse[AlertResponse],
    summary="Dismiss alert",
    description="Dismiss an alert for the authenticated user.",
)
def dismiss_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertResponse]:
    return success(AlertService(db).dismiss_response(alert_id, current_user.id))
