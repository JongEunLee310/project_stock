from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.db.session import get_db
from app.domains.alerts.schema import AlertResponse
from app.domains.alerts.service import AlertService
from app.domains.alerts.types import AlertStatus
from app.domains.users.model import User

router = APIRouter()


@router.get("", response_model=list[AlertResponse])
def list_alerts(
    status: AlertStatus | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[AlertResponse]:
    status_value = status.value if status is not None else None
    return [
        AlertResponse.model_validate(alert)
        for alert in AlertService(db).list_alerts(current_user.id, status_value)
    ]


@router.post("/{alert_id}/read", response_model=AlertResponse)
def mark_alert_read(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    return AlertResponse.model_validate(
        AlertService(db).mark_read(alert_id, current_user.id)
    )


@router.post("/{alert_id}/dismiss", response_model=AlertResponse)
def dismiss_alert(
    alert_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertResponse:
    return AlertResponse.model_validate(
        AlertService(db).dismiss(alert_id, current_user.id)
    )
