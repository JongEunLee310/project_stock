from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.pagination import PaginationParams, SortParams, sort_param
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alert_events.schema import (
    AlertEventDetailProjection,
    AlertEventProjection,
    AlertEventReadRequest,
)
from app.domains.alert_events.service import AlertEventService
from app.domains.alert_rules.types import AlertSeverity, AlertTargetType
from app.domains.users.model import User

router = APIRouter()
alert_event_sort = sort_param(
    allowed_fields={"id", "severity", "triggered_at"},
    default="-triggered_at",
)


@router.get(
    "",
    response_model=ApiResponse[list[AlertEventProjection]],
    summary="List alert events",
)
def list_alert_events(
    pagination: Annotated[PaginationParams, Depends()],
    sort: Annotated[SortParams, Depends(alert_event_sort)],
    severity: AlertSeverity | None = None,
    read: bool | None = None,
    target_type: AlertTargetType | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertEventProjection]]:
    service = AlertEventService(db)
    items = service.list_events(
        current_user.id,
        severity=severity,
        read=read,
        target_type=target_type,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort.value,
    )
    total = service.count_events(
        current_user.id,
        severity=severity,
        read=read,
        target_type=target_type,
    )
    return paginated(
        items,
        page=pagination.page,
        size=pagination.size,
        total=total,
    )


@router.post(
    "/read",
    response_model=ApiResponse[list[AlertEventProjection]],
    summary="Mark alert events read",
)
def mark_alert_events_read(
    data: AlertEventReadRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertEventProjection]]:
    return success(
        AlertEventService(db).mark_many_read(data.alert_ids, current_user.id)
    )


@router.get(
    "/{alert_event_id}",
    response_model=ApiResponse[AlertEventDetailProjection],
    summary="Get alert event",
)
def get_alert_event(
    alert_event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertEventDetailProjection]:
    return success(AlertEventService(db).get_event(alert_event_id, current_user.id))


@router.post(
    "/{alert_event_id}/read",
    response_model=ApiResponse[AlertEventProjection],
    summary="Mark alert event read",
)
def mark_alert_event_read(
    alert_event_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertEventProjection]:
    return success(AlertEventService(db).mark_read(alert_event_id, current_user.id))
