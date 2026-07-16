from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domains.alert_events.model import AlertEvent


class AlertEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, alert_event_id: int) -> AlertEvent | None:
        return self.db.get(AlertEvent, alert_event_id)

    def get_by_ids(self, alert_event_ids: list[int]) -> list[AlertEvent]:
        stmt = select(AlertEvent).where(AlertEvent.id.in_(alert_event_ids))
        return list(self.db.scalars(stmt).all())

    def list_by_user(
        self,
        user_id: int,
        *,
        severity: str | None = None,
        read: bool | None = None,
        target_type: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-triggered_at",
    ) -> list[AlertEvent]:
        stmt = select(AlertEvent).where(AlertEvent.user_id == user_id)
        stmt = self._apply_filters(
            stmt,
            severity=severity,
            read=read,
            target_type=target_type,
        )
        stmt = self._apply_sort(stmt, sort).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(
        self,
        user_id: int,
        *,
        severity: str | None = None,
        read: bool | None = None,
        target_type: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AlertEvent).where(
            AlertEvent.user_id == user_id
        )
        stmt = self._apply_filters(
            stmt,
            severity=severity,
            read=read,
            target_type=target_type,
        )
        return int(self.db.scalar(stmt) or 0)

    def mark_read(
        self,
        alert_events: list[AlertEvent],
        *,
        read_at: datetime,
    ) -> list[AlertEvent]:
        for alert_event in alert_events:
            if alert_event.read_at is None:
                alert_event.read_at = read_at
        self.db.commit()
        for alert_event in alert_events:
            self.db.refresh(alert_event)
        return alert_events

    def _apply_filters(
        self,
        stmt: Select[Any],
        *,
        severity: str | None,
        read: bool | None,
        target_type: str | None,
    ) -> Select[Any]:
        if severity is not None:
            stmt = stmt.where(AlertEvent.severity == severity)
        if read is True:
            stmt = stmt.where(AlertEvent.read_at.is_not(None))
        elif read is False:
            stmt = stmt.where(AlertEvent.read_at.is_(None))
        if target_type is not None:
            stmt = stmt.where(AlertEvent.target_type == target_type)
        return stmt

    def _apply_sort(
        self,
        stmt: Select[tuple[AlertEvent]],
        sort: str,
    ) -> Select[tuple[AlertEvent]]:
        columns = {
            "id": AlertEvent.id,
            "severity": AlertEvent.severity,
            "triggered_at": AlertEvent.triggered_at,
        }
        descending = sort.startswith("-")
        field = sort[1:] if descending else sort
        column = columns[field]
        if descending:
            return stmt.order_by(column.desc(), AlertEvent.id.desc())
        return stmt.order_by(column, AlertEvent.id)
