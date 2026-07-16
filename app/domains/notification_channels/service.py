from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.alert_rules.types import AlertChannel
from app.domains.notification_channels.model import NotificationChannel
from app.domains.notification_channels.repository import NotificationChannelRepository
from app.domains.notification_channels.schema import (
    NotificationChannelCreate,
    NotificationChannelProjection,
)

_EMAIL_ADAPTER = TypeAdapter(EmailStr)


class NotificationChannelService:
    def __init__(self, db: Session) -> None:
        self.repo = NotificationChannelRepository(db)

    def list_channels(self, user_id: int) -> list[NotificationChannelProjection]:
        if not self.repo.has_app_channel(user_id):
            self.repo.create(
                user_id,
                channel_type=AlertChannel.APP.value,
                configuration={},
            )
        return [
            NotificationChannelProjection.model_validate(channel)
            for channel in self.repo.list_by_user(user_id)
        ]

    def create_channel(
        self,
        user_id: int,
        data: NotificationChannelCreate,
    ) -> NotificationChannelProjection:
        configuration = self._validated_configuration(data)
        if data.channel_type == AlertChannel.APP and self.repo.has_app_channel(user_id):
            raise self._validation_error("APP 알림 채널은 중복 등록할 수 없습니다.")
        channel = self.repo.create(
            user_id,
            channel_type=data.channel_type.value,
            configuration=configuration,
        )
        return NotificationChannelProjection.model_validate(channel)

    def get_channel(
        self,
        notification_channel_id: int,
        user_id: int,
    ) -> NotificationChannelProjection:
        channel = self._get_owned_channel(notification_channel_id, user_id)
        return NotificationChannelProjection.model_validate(channel)

    def _validated_configuration(
        self,
        data: NotificationChannelCreate,
    ) -> dict[str, str]:
        if data.channel_type in {AlertChannel.DISCORD, AlertChannel.SLACK}:
            raise self._validation_error("아직 지원하지 않는 알림 채널입니다.")
        if data.channel_type == AlertChannel.APP:
            if data.configuration:
                raise self._validation_error("APP 알림 채널에는 설정이 필요하지 않습니다.")
            return {}
        if set(data.configuration) != {"email"}:
            raise self._validation_error("EMAIL 알림 채널에는 이메일 주소가 필요합니다.")
        try:
            email = _EMAIL_ADAPTER.validate_python(data.configuration["email"])
        except ValidationError as exc:
            raise self._validation_error(
                "EMAIL 알림 채널의 이메일 주소가 올바르지 않습니다."
            ) from exc
        return {"email": str(email)}

    def _get_owned_channel(
        self,
        notification_channel_id: int,
        user_id: int,
    ) -> NotificationChannel:
        channel = self.repo.get_by_id(notification_channel_id)
        if channel is None:
            raise AppException(
                status_code=404,
                detail="알림 채널을 찾을 수 없습니다.",
                error_code=ErrorCode.NOTIFICATION_CHANNEL_NOT_FOUND,
            )
        if channel.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="알림 채널 접근 권한이 없습니다.",
                error_code=ErrorCode.NOTIFICATION_CHANNEL_FORBIDDEN,
            )
        return channel

    def _validation_error(self, detail: str) -> AppException:
        return AppException(
            status_code=422,
            detail=detail,
            error_code=ErrorCode.VALIDATION_ERROR,
        )
