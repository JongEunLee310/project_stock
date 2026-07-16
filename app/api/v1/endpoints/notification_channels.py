from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_user
from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.notification_channels.schema import (
    NotificationChannelCreate,
    NotificationChannelProjection,
)
from app.domains.notification_channels.service import NotificationChannelService
from app.domains.users.model import User

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse[list[NotificationChannelProjection]],
    summary="List notification channels",
)
def list_notification_channels(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[list[NotificationChannelProjection]]:
    return success(NotificationChannelService(db).list_channels(current_user.id))


@router.post(
    "",
    response_model=ApiResponse[NotificationChannelProjection],
    status_code=201,
    summary="Create notification channel",
)
def create_notification_channel(
    data: NotificationChannelCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ApiResponse[NotificationChannelProjection]:
    return success(
        NotificationChannelService(db).create_channel(current_user.id, data)
    )
