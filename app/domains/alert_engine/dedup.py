import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.domains.alert_engine.types import AlertEvaluationResult
from app.domains.alert_events.model import AlertEvent
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertDeliveryPolicy


class AlertDedupService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def should_emit(
        self,
        rule: AlertRule,
        result: AlertEvaluationResult,
        *,
        asset_id: int | None,
        now: datetime,
    ) -> bool:
        if not result.matched:
            return False
        if self._in_cooldown(rule, asset_id, now):
            return False
        policy = AlertDeliveryPolicy(rule.delivery_policy)
        if policy == AlertDeliveryPolicy.ONCE_PER_TRANSITION and not result.is_transition:
            return False
        if policy == AlertDeliveryPolicy.ONCE_PER_DAY and self._emitted_today(
            rule,
            asset_id,
            now,
        ):
            return False
        dedup_key = self.build_dedup_key(
            rule,
            result,
            asset_id=asset_id,
            now=now,
        )
        return not self._dedup_key_exists(rule.user_id, dedup_key)

    def build_dedup_key(
        self,
        rule: AlertRule,
        result: AlertEvaluationResult,
        *,
        asset_id: int | None,
        now: datetime,
    ) -> str:
        fingerprint = result.event_fingerprint
        if rule.delivery_policy == AlertDeliveryPolicy.ONCE_PER_DAY.value:
            fingerprint = f"{fingerprint}:{self._as_utc(now).date().isoformat()}"
        digest = hashlib.sha256(fingerprint.encode()).hexdigest()
        target_id = rule.target_id if rule.target_id is not None else "-"
        asset_key = str(asset_id) if asset_id is not None else "-"
        return f"{rule.id}:{target_id}:{asset_key}:{digest}"

    def _in_cooldown(
        self,
        rule: AlertRule,
        asset_id: int | None,
        now: datetime,
    ) -> bool:
        if rule.cooldown_seconds <= 0:
            return False
        last_triggered_at = self.db.scalar(
            select(func.max(AlertEvent.triggered_at)).where(
                AlertEvent.rule_id == rule.id,
                self._asset_filter(asset_id),
            )
        )
        if last_triggered_at is None:
            return False
        cooldown_ends_at = self._as_utc(last_triggered_at) + timedelta(
            seconds=rule.cooldown_seconds
        )
        return self._as_utc(now) < cooldown_ends_at

    def _emitted_today(
        self,
        rule: AlertRule,
        asset_id: int | None,
        now: datetime,
    ) -> bool:
        utc_now = self._as_utc(now)
        day_start = utc_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        stmt = (
            select(AlertEvent.id)
            .where(
                AlertEvent.rule_id == rule.id,
                AlertEvent.target_id == rule.target_id,
                self._asset_filter(asset_id),
                AlertEvent.triggered_at >= day_start,
                AlertEvent.triggered_at < day_end,
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def _asset_filter(self, asset_id: int | None) -> ColumnElement[bool]:
        if asset_id is None:
            return AlertEvent.asset_id.is_(None)
        return AlertEvent.asset_id == asset_id

    def _dedup_key_exists(self, user_id: int, dedup_key: str) -> bool:
        stmt = (
            select(AlertEvent.id)
            .where(
                AlertEvent.user_id == user_id,
                AlertEvent.dedup_key == dedup_key,
            )
            .limit(1)
        )
        return self.db.scalar(stmt) is not None

    def _as_utc(self, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
