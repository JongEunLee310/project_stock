from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.alert_engine.dedup import AlertDedupService
from app.domains.alert_engine.evaluator import AlertEvaluator
from app.domains.alert_engine.snapshot_provider import MetricSnapshotProvider
from app.domains.alert_engine.types import (
    AlertCycleSummary,
    AlertEvaluationResult,
    SnapshotProvider,
)
from app.domains.alert_events.model import AlertDelivery, AlertEvent
from app.domains.alert_events.types import AlertDeliveryStatus
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertChannel


class AlertEngineService:
    def __init__(
        self,
        db: Session,
        *,
        snapshot_provider: SnapshotProvider | None = None,
    ) -> None:
        self.db = db
        self.snapshot_provider = snapshot_provider or MetricSnapshotProvider(db)
        self.evaluator = AlertEvaluator()
        self.dedup = AlertDedupService(db)

    def run_cycle(self, *, now: datetime | None = None) -> AlertCycleSummary:
        evaluated_at = now or datetime.now(UTC)
        counters = {
            "evaluated_count": 0,
            "matched_count": 0,
            "emitted_count": 0,
            "deduplicated_count": 0,
            "unsupported_count": 0,
            "unavailable_count": 0,
        }
        rules = list(
            self.db.scalars(
                select(AlertRule)
                .where(AlertRule.enabled.is_(True))
                .order_by(AlertRule.id)
            ).all()
        )
        for rule in rules:
            counters["evaluated_count"] += 1
            snapshot = self.snapshot_provider.get_snapshot(rule, as_of=evaluated_at)
            result = self.evaluator.evaluate_rule(rule, snapshot)
            if result.unsupported_metrics:
                counters["unsupported_count"] += 1
                continue
            if result.unavailable_metrics:
                counters["unavailable_count"] += 1
                continue
            if not result.matched:
                continue
            counters["matched_count"] += 1
            if not self.dedup.should_emit(rule, result, now=evaluated_at):
                counters["deduplicated_count"] += 1
                continue
            dedup_key = self.dedup.build_dedup_key(rule, result, now=evaluated_at)
            if not self._create_event(rule, snapshot.asset_id, result, dedup_key, evaluated_at):
                counters["deduplicated_count"] += 1
                continue
            rule.last_triggered_at = evaluated_at
            counters["emitted_count"] += 1
        self.db.flush()
        return AlertCycleSummary(
            evaluated_count=counters["evaluated_count"],
            matched_count=counters["matched_count"],
            emitted_count=counters["emitted_count"],
            deduplicated_count=counters["deduplicated_count"],
            unsupported_count=counters["unsupported_count"],
            unavailable_count=counters["unavailable_count"],
        )

    def _create_event(
        self,
        rule: AlertRule,
        asset_id: int | None,
        result: AlertEvaluationResult,
        dedup_key: str,
        triggered_at: datetime,
    ) -> bool:
        target_label = rule.target_id or rule.target_type
        try:
            with self.db.begin_nested():
                event = AlertEvent(
                    rule_id=rule.id,
                    user_id=rule.user_id,
                    target_type=rule.target_type,
                    target_id=rule.target_id,
                    asset_id=asset_id,
                    title=rule.name,
                    message=f"{target_label} 대상 알림 조건이 충족되었습니다.",
                    severity=rule.severity,
                    triggered_value=result.triggered_value,
                    evidence=result.evidence,
                    dedup_key=dedup_key,
                    triggered_at=triggered_at,
                )
                self.db.add(event)
                self.db.flush()
                for channel in dict.fromkeys(rule.channels):
                    is_app = channel == AlertChannel.APP.value
                    self.db.add(
                        AlertDelivery(
                            alert_event_id=event.id,
                            channel=channel,
                            status=(
                                AlertDeliveryStatus.SUCCESS.value
                                if is_app
                                else AlertDeliveryStatus.PENDING.value
                            ),
                            attempted_at=triggered_at,
                            delivered_at=triggered_at if is_app else None,
                        )
                    )
                self.db.flush()
        except IntegrityError:
            return False
        return True
