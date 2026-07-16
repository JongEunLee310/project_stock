from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.alert_events.model import AlertEvent
from app.domains.alert_events.repository import AlertEventRepository
from app.domains.alert_events.schema import (
    AlertEventDetailProjection,
    AlertEventProjection,
)
from app.domains.alert_rules.types import AlertSeverity, AlertTargetType


class AlertEventService:
    def __init__(self, db: Session) -> None:
        self.repo = AlertEventRepository(db)

    def list_events(
        self,
        user_id: int,
        *,
        severity: AlertSeverity | None = None,
        read: bool | None = None,
        target_type: AlertTargetType | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-triggered_at",
    ) -> list[AlertEventProjection]:
        return [
            AlertEventProjection.model_validate(alert_event)
            for alert_event in self.repo.list_by_user(
                user_id,
                severity=severity.value if severity is not None else None,
                read=read,
                target_type=target_type.value if target_type is not None else None,
                offset=offset,
                limit=limit,
                sort=sort,
            )
        ]

    def count_events(
        self,
        user_id: int,
        *,
        severity: AlertSeverity | None = None,
        read: bool | None = None,
        target_type: AlertTargetType | None = None,
    ) -> int:
        return self.repo.count_by_user(
            user_id,
            severity=severity.value if severity is not None else None,
            read=read,
            target_type=target_type.value if target_type is not None else None,
        )

    def get_event(self, alert_event_id: int, user_id: int) -> AlertEventDetailProjection:
        alert_event = self._get_owned_event(alert_event_id, user_id)
        return AlertEventDetailProjection.model_validate(alert_event)

    def mark_read(self, alert_event_id: int, user_id: int) -> AlertEventProjection:
        alert_event = self._get_owned_event(alert_event_id, user_id)
        updated = self.repo.mark_read([alert_event], read_at=datetime.now(UTC))[0]
        return AlertEventProjection.model_validate(updated)

    def mark_many_read(
        self,
        alert_event_ids: list[int],
        user_id: int,
    ) -> list[AlertEventProjection]:
        unique_ids = list(dict.fromkeys(alert_event_ids))
        events_by_id = {
            alert_event.id: alert_event
            for alert_event in self.repo.get_by_ids(unique_ids)
        }
        alert_events = [
            self._require_owned_event(events_by_id.get(alert_event_id), user_id)
            for alert_event_id in unique_ids
        ]
        updated = self.repo.mark_read(alert_events, read_at=datetime.now(UTC))
        return [AlertEventProjection.model_validate(alert_event) for alert_event in updated]

    def _get_owned_event(self, alert_event_id: int, user_id: int) -> AlertEvent:
        return self._require_owned_event(self.repo.get_by_id(alert_event_id), user_id)

    def _require_owned_event(
        self,
        alert_event: AlertEvent | None,
        user_id: int,
    ) -> AlertEvent:
        if alert_event is None:
            raise AppException(
                status_code=404,
                detail="알림 이벤트를 찾을 수 없습니다.",
                error_code=ErrorCode.ALERT_EVENT_NOT_FOUND,
            )
        if alert_event.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="알림 이벤트 접근 권한이 없습니다.",
                error_code=ErrorCode.ALERT_EVENT_FORBIDDEN,
            )
        return alert_event
