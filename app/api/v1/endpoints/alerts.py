from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, paginated, success
from app.db.session import get_db
from app.domains.alerts.schema import AlertResponse
from app.domains.alerts.service import AlertService
from app.domains.alerts.types import AlertStatus
from app.domains.users.model import User

router = APIRouter()


@router.get("", response_model=ApiResponse[list[AlertResponse]])
def list_alerts(
    status: AlertStatus | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    size: Annotated[int, Query(ge=1, le=100)] = 20,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[AlertResponse]]:
    status_value = status.value if status is not None else None
    service = AlertService(db)
    items = [
        AlertResponse.model_validate(alert)
        for alert in service.list_alerts(
            current_user.id,
            status_value,
            offset=(page - 1) * size,
            limit=size,
        )
    ]
    total = service.count_alerts(current_user.id, status_value)
    return paginated(items, page=page, size=size, total=total)


@router.post("/{alert_id}/read", response_model=ApiResponse[AlertResponse])
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertResponse]:
    return success(
        AlertResponse.model_validate(
            AlertService(db).mark_read(alert_id, current_user.id)
        )
    )


@router.post("/{alert_id}/dismiss", response_model=ApiResponse[AlertResponse])
def dismiss_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[AlertResponse]:
    return success(
        AlertResponse.model_validate(
            AlertService(db).dismiss(alert_id, current_user.id)
        )
    )
