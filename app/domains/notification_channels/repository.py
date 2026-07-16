from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.notification_channels.model import NotificationChannel


class NotificationChannelRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, notification_channel_id: int) -> NotificationChannel | None:
        return self.db.get(NotificationChannel, notification_channel_id)

    def list_by_user(self, user_id: int) -> list[NotificationChannel]:
        stmt = (
            select(NotificationChannel)
            .where(NotificationChannel.user_id == user_id)
            .order_by(NotificationChannel.id)
        )
        return list(self.db.scalars(stmt).all())

    def get_by_user_and_type(
        self,
        user_id: int,
        channel_type: str,
    ) -> NotificationChannel | None:
        stmt = select(NotificationChannel).where(
            NotificationChannel.user_id == user_id,
            NotificationChannel.channel_type == channel_type,
        )
        return self.db.scalars(stmt).first()

    def has_app_channel(self, user_id: int) -> bool:
        return self.get_by_user_and_type(user_id, "APP") is not None

    def create(
        self,
        user_id: int,
        *,
        channel_type: str,
        configuration: dict[str, Any],
    ) -> NotificationChannel:
        notification_channel = NotificationChannel(
            user_id=user_id,
            channel_type=channel_type,
            configuration=configuration,
            enabled=True,
            verified_at=None,
        )
        self.db.add(notification_channel)
        self.db.commit()
        self.db.refresh(notification_channel)
        return notification_channel
