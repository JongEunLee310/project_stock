from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domains.alert_events.model import AlertEvent
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.schema import AlertRuleUpdate


class AlertRuleRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, alert_rule_id: int) -> AlertRule | None:
        return self.db.get(AlertRule, alert_rule_id)

    def list_by_user(
        self,
        user_id: int,
        *,
        enabled: bool | None = None,
        target_type: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
    ) -> list[AlertRule]:
        stmt = select(AlertRule).where(AlertRule.user_id == user_id)
        stmt = self._apply_filters(stmt, enabled=enabled, target_type=target_type)
        stmt = self._apply_sort(stmt, sort).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(
        self,
        user_id: int,
        *,
        enabled: bool | None = None,
        target_type: str | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(AlertRule).where(AlertRule.user_id == user_id)
        stmt = self._apply_filters(stmt, enabled=enabled, target_type=target_type)
        return int(self.db.scalar(stmt) or 0)

    def create(self, user_id: int, values: dict[str, object]) -> AlertRule:
        alert_rule = AlertRule(user_id=user_id, **values)
        self.db.add(alert_rule)
        self.db.commit()
        self.db.refresh(alert_rule)
        return alert_rule

    def update(self, alert_rule: AlertRule, data: AlertRuleUpdate) -> AlertRule:
        values = data.model_dump(exclude_unset=True)
        for field, value in values.items():
            if hasattr(value, "value"):
                value = value.value
            if field == "channels" and value is not None:
                value = [channel.value for channel in value]
            setattr(alert_rule, field, value)
        self.db.commit()
        self.db.refresh(alert_rule)
        return alert_rule

    def set_enabled(self, alert_rule: AlertRule, *, enabled: bool) -> AlertRule:
        alert_rule.enabled = enabled
        self.db.commit()
        self.db.refresh(alert_rule)
        return alert_rule

    def delete(self, alert_rule: AlertRule) -> None:
        self.db.delete(alert_rule)
        self.db.commit()

    def count_events_triggered_since(self, user_id: int, since: datetime) -> int:
        stmt = (
            select(func.count())
            .select_from(AlertEvent)
            .where(
                AlertEvent.user_id == user_id,
                AlertEvent.triggered_at >= since,
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def count_high_severity_events(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(AlertEvent)
            .where(
                AlertEvent.user_id == user_id,
                AlertEvent.severity.in_(("HIGH", "CRITICAL")),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def count_unread_events(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(AlertEvent)
            .where(
                AlertEvent.user_id == user_id,
                AlertEvent.read_at.is_(None),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def _apply_filters(
        self,
        stmt: Select[Any],
        *,
        enabled: bool | None,
        target_type: str | None,
    ) -> Select[Any]:
        if enabled is not None:
            stmt = stmt.where(AlertRule.enabled.is_(enabled))
        if target_type is not None:
            stmt = stmt.where(AlertRule.target_type == target_type)
        return stmt

    def _apply_sort(
        self,
        stmt: Select[tuple[AlertRule]],
        sort: str,
    ) -> Select[tuple[AlertRule]]:
        if sort == "created_at":
            return stmt.order_by(AlertRule.created_at, AlertRule.id)
        if sort == "name":
            return stmt.order_by(AlertRule.name, AlertRule.id)
        if sort == "-name":
            return stmt.order_by(AlertRule.name.desc(), AlertRule.id.desc())
        return stmt.order_by(AlertRule.created_at.desc(), AlertRule.id.desc())
