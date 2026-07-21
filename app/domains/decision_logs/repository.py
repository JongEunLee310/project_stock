from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum

from sqlalchemy import Select, case, func, or_, select
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.orm import Session

from app.domains.decision_logs.model import (
    DecisionEvidence,
    DecisionLog,
    DecisionReviewTrigger,
    DecisionRisk,
    DecisionSnapshot,
)
from app.domains.decision_logs.schema import (
    DecisionEvidenceInput,
    DecisionLogCreate,
    DecisionLogUpdate,
    DecisionSnapshotInput,
)
from app.domains.decision_logs.types import (
    DecisionStatus,
    ReviewTriggerStatus,
    ReviewTriggerType,
)


@dataclass(frozen=True)
class OverviewAgg:
    total_count: int
    created_this_week: int
    review_due_count: int
    active_count: int
    decision_type_counts: dict[str, int]


class DecisionLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, decision_log_id: int) -> DecisionLog | None:
        return self.db.get(DecisionLog, decision_log_id)

    def get_owned(self, decision_log_id: int, user_id: int) -> DecisionLog | None:
        stmt = select(DecisionLog).where(
            DecisionLog.id == decision_log_id,
            DecisionLog.user_id == user_id,
        )
        return self.db.scalar(stmt)

    def list_by_user(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
        *,
        target_type: str | None = None,
        symbol: str | None = None,
        decision_type: str | None = None,
        status: str | None = None,
        risk_type: str | None = None,
        review_due_before: datetime | None = None,
    ) -> list[DecisionLog]:
        stmt = select(DecisionLog).where(
            *self._filter_conditions(
                user_id,
                target_type=target_type,
                symbol=symbol,
                decision_type=decision_type,
                status=status,
                risk_type=risk_type,
                review_due_before=review_due_before,
            )
        )
        stmt = self._apply_sort(stmt, sort).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(
        self,
        user_id: int,
        *,
        target_type: str | None = None,
        symbol: str | None = None,
        decision_type: str | None = None,
        status: str | None = None,
        risk_type: str | None = None,
        review_due_before: datetime | None = None,
    ) -> int:
        stmt = select(func.count()).select_from(DecisionLog).where(
            *self._filter_conditions(
                user_id,
                target_type=target_type,
                symbol=symbol,
                decision_type=decision_type,
                status=status,
                risk_type=risk_type,
                review_due_before=review_due_before,
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def list_review_due(
        self,
        user_id: int,
        now: datetime,
        *,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[DecisionLog]:
        review_at = self._pending_date_review_at()
        stmt = (
            select(DecisionLog)
            .where(
                DecisionLog.user_id == user_id,
                or_(
                    DecisionLog.status == DecisionStatus.REVIEW_DUE.value,
                    review_at <= now,
                ),
            )
            .order_by(review_at.asc().nullslast(), DecisionLog.id)
            .offset(offset)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_review_due(self, user_id: int, now: datetime) -> int:
        review_at = self._pending_date_review_at()
        stmt = (
            select(func.count())
            .select_from(DecisionLog)
            .where(
                DecisionLog.user_id == user_id,
                or_(
                    DecisionLog.status == DecisionStatus.REVIEW_DUE.value,
                    review_at <= now,
                ),
            )
        )
        return int(self.db.scalar(stmt) or 0)

    def list_risk_types_by_decision(
        self,
        decision_log_ids: list[int],
    ) -> dict[int, list[str]]:
        risks_by_decision: dict[int, list[str]] = {
            decision_id: [] for decision_id in decision_log_ids
        }
        if not decision_log_ids:
            return risks_by_decision
        stmt = (
            select(DecisionRisk.decision_id, DecisionRisk.risk_type)
            .where(DecisionRisk.decision_id.in_(decision_log_ids))
            .order_by(DecisionRisk.decision_id, DecisionRisk.id)
        )
        for decision_id, risk_type in self.db.execute(stmt):
            risks_by_decision[int(decision_id)].append(str(risk_type))
        return risks_by_decision

    def list_review_at_by_decision(
        self,
        decision_log_ids: list[int],
    ) -> dict[int, datetime]:
        if not decision_log_ids:
            return {}
        stmt = (
            select(
                DecisionReviewTrigger.decision_id,
                func.min(DecisionReviewTrigger.scheduled_at),
            )
            .where(
                DecisionReviewTrigger.decision_id.in_(decision_log_ids),
                DecisionReviewTrigger.trigger_type == ReviewTriggerType.DATE.value,
                DecisionReviewTrigger.status == ReviewTriggerStatus.PENDING.value,
                DecisionReviewTrigger.scheduled_at.is_not(None),
            )
            .group_by(DecisionReviewTrigger.decision_id)
        )
        return {
            int(decision_id): review_at
            for decision_id, review_at in self.db.execute(stmt)
            if review_at is not None
        }

    def aggregate_overview(self, user_id: int, now: datetime) -> OverviewAgg:
        # A rolling seven-day window avoids week-boundary and timezone ambiguity.
        week_start = now - timedelta(days=7)
        counts_stmt = select(
            func.count(DecisionLog.id),
            func.sum(
                case((DecisionLog.created_at >= week_start, 1), else_=0)
            ),
            func.sum(
                case(
                    (
                        DecisionLog.status.in_(
                            (
                                DecisionStatus.ACTIVE.value,
                                DecisionStatus.REVIEW_DUE.value,
                            )
                        ),
                        1,
                    ),
                    else_=0,
                )
            ),
        ).where(DecisionLog.user_id == user_id)
        total_count, created_this_week, active_count = self.db.execute(
            counts_stmt
        ).one()

        review_at = self._pending_date_review_at()
        review_due_stmt = select(func.count()).select_from(DecisionLog).where(
            DecisionLog.user_id == user_id,
            or_(
                DecisionLog.status == DecisionStatus.REVIEW_DUE.value,
                review_at <= now,
            ),
        )
        review_due_count = self.db.scalar(review_due_stmt)

        type_count = func.count(DecisionLog.id).label("type_count")
        stmt = (
            select(DecisionLog.decision_type, type_count)
            .where(DecisionLog.user_id == user_id)
            .group_by(DecisionLog.decision_type)
            .order_by(type_count.desc(), DecisionLog.decision_type)
        )
        decision_type_counts = {
            str(decision_type): int(count)
            for decision_type, count in self.db.execute(stmt).all()
        }
        return OverviewAgg(
            total_count=int(total_count or 0),
            created_this_week=int(created_this_week or 0),
            review_due_count=int(review_due_count or 0),
            active_count=int(active_count or 0),
            decision_type_counts=decision_type_counts,
        )

    def create(
        self,
        user_id: int,
        data: DecisionLogCreate,
        evidence: list[DecisionEvidenceInput] | None = None,
    ) -> DecisionLog:
        evidence_items = data.evidence if evidence is None else evidence
        decision_log = DecisionLog(
            user_id=user_id,
            target_type=data.target.type.value,
            target_id=data.target.id,
            symbol=data.target.id if data.target.type.value == "SYMBOL" else None,
            decision_type=data.decision_type.value,
            status=DecisionStatus.DRAFT.value,
            thesis=data.thesis,
            rationale=data.rationale,
            confidence_level=(
                data.confidence_level.value
                if data.confidence_level is not None
                else None
            ),
            created_by=data.created_by.value,
        )
        self.db.add(decision_log)
        self.db.flush()
        self.db.add_all(
            [self._evidence_model(decision_log.id, item) for item in evidence_items]
            + [
                DecisionRisk(
                    decision_id=decision_log.id,
                    risk_type=item.type,
                    description=item.description,
                    severity=item.severity.value,
                )
                for item in data.risks
            ]
            + [
                DecisionReviewTrigger(
                    decision_id=decision_log.id,
                    trigger_type=item.type.value,
                    condition=item.condition,
                    scheduled_at=item.scheduled_at,
                    status=ReviewTriggerStatus.PENDING.value,
                )
                for item in data.review_triggers
            ]
        )
        self.db.commit()
        self.db.refresh(decision_log)
        return decision_log

    def update(self, decision_log: DecisionLog, data: DecisionLogUpdate) -> DecisionLog:
        values = data.model_dump(exclude_unset=True, exclude={"target"})
        for enum_field in ("decision_type", "confidence_level", "created_by"):
            if isinstance(values.get(enum_field), Enum):
                values[enum_field] = values[enum_field].value
        if "target" in data.model_fields_set and data.target is not None:
            values.update(
                target_type=data.target.type.value,
                target_id=data.target.id,
                symbol=data.target.id if data.target.type.value == "SYMBOL" else None,
            )
        for field, value in values.items():
            setattr(decision_log, field, value)
        self.db.commit()
        self.db.refresh(decision_log)
        return decision_log

    def activate(
        self,
        decision_log: DecisionLog,
        activated_at: datetime,
        snapshots: list[DecisionSnapshotInput],
    ) -> DecisionLog:
        decision_log.status = DecisionStatus.ACTIVE.value
        decision_log.activated_at = activated_at
        decision_log.decided_at = activated_at
        for trigger in self.list_review_triggers(decision_log.id):
            if trigger.trigger_type == "DATE":
                trigger.status = ReviewTriggerStatus.PENDING.value
        self.add_snapshots(decision_log.id, snapshots, captured_at=activated_at)
        self.db.commit()
        self.db.refresh(decision_log)
        return decision_log

    def add_snapshots(
        self,
        decision_log_id: int,
        items: list[DecisionSnapshotInput],
        *,
        captured_at: datetime | None = None,
    ) -> None:
        capture_time = captured_at or datetime.now(UTC)
        self.db.add_all(
            [
                DecisionSnapshot(
                    decision_id=decision_log_id,
                    snapshot_type=item.snapshot_type,
                    data=item.data,
                    captured_at=capture_time,
                )
                for item in items
            ]
        )

    def list_evidence(self, decision_log_id: int) -> list[DecisionEvidence]:
        stmt = (
            select(DecisionEvidence)
            .where(DecisionEvidence.decision_id == decision_log_id)
            .order_by(DecisionEvidence.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_risks(self, decision_log_id: int) -> list[DecisionRisk]:
        stmt = (
            select(DecisionRisk)
            .where(DecisionRisk.decision_id == decision_log_id)
            .order_by(DecisionRisk.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_review_triggers(self, decision_log_id: int) -> list[DecisionReviewTrigger]:
        stmt = (
            select(DecisionReviewTrigger)
            .where(DecisionReviewTrigger.decision_id == decision_log_id)
            .order_by(DecisionReviewTrigger.id)
        )
        return list(self.db.scalars(stmt).all())

    def list_pending_event_triggers(
        self,
    ) -> list[tuple[DecisionLog, DecisionReviewTrigger]]:
        stmt = (
            select(DecisionLog, DecisionReviewTrigger)
            .join(
                DecisionReviewTrigger,
                DecisionReviewTrigger.decision_id == DecisionLog.id,
            )
            .where(
                DecisionLog.status == DecisionStatus.ACTIVE.value,
                DecisionReviewTrigger.status == ReviewTriggerStatus.PENDING.value,
                DecisionReviewTrigger.trigger_type.in_(
                    (
                        ReviewTriggerType.PRICE.value,
                        ReviewTriggerType.SIGNAL_CHANGE.value,
                    )
                ),
            )
            .order_by(DecisionReviewTrigger.id)
        )
        return [(decision, trigger) for decision, trigger in self.db.execute(stmt)]

    def mark_triggered(
        self,
        decision_log: DecisionLog,
        trigger: DecisionReviewTrigger,
        at: datetime,
    ) -> bool:
        trigger.status = ReviewTriggerStatus.TRIGGERED.value
        trigger.triggered_at = at
        if decision_log.status != DecisionStatus.ACTIVE.value:
            return False
        decision_log.status = DecisionStatus.REVIEW_DUE.value
        return True

    def list_snapshots(self, decision_log_id: int) -> list[DecisionSnapshot]:
        stmt = (
            select(DecisionSnapshot)
            .where(DecisionSnapshot.decision_id == decision_log_id)
            .order_by(DecisionSnapshot.id)
        )
        return list(self.db.scalars(stmt).all())

    @staticmethod
    def _evidence_model(
        decision_log_id: int,
        item: DecisionEvidenceInput,
    ) -> DecisionEvidence:
        title = item.title or item.summary or item.id or item.type
        return DecisionEvidence(
            decision_id=decision_log_id,
            evidence_type=item.type,
            evidence_id=item.id,
            evidence_version=item.version,
            title=title,
            summary=item.summary,
            snapshot=item.snapshot,
            relationship=item.relationship.value,
        )

    def _apply_sort(
        self,
        stmt: Select[tuple[DecisionLog]],
        sort: str,
    ) -> Select[tuple[DecisionLog]]:
        if sort == "created_at":
            return stmt.order_by(DecisionLog.created_at, DecisionLog.id)
        if sort == "-created_at":
            return stmt.order_by(DecisionLog.created_at.desc(), DecisionLog.id.desc())
        if sort == "decided_at":
            return stmt.order_by(DecisionLog.decided_at, DecisionLog.id)
        return stmt.order_by(DecisionLog.decided_at.desc(), DecisionLog.id.desc())

    @staticmethod
    def _pending_date_review_at() -> ColumnElement[datetime | None]:
        return (
            select(func.min(DecisionReviewTrigger.scheduled_at))
            .where(
                DecisionReviewTrigger.decision_id == DecisionLog.id,
                DecisionReviewTrigger.trigger_type == ReviewTriggerType.DATE.value,
                DecisionReviewTrigger.status == ReviewTriggerStatus.PENDING.value,
                DecisionReviewTrigger.scheduled_at.is_not(None),
            )
            .correlate(DecisionLog)
            .scalar_subquery()
        )

    @classmethod
    def _filter_conditions(
        cls,
        user_id: int,
        *,
        target_type: str | None,
        symbol: str | None,
        decision_type: str | None,
        status: str | None,
        risk_type: str | None,
        review_due_before: datetime | None,
    ) -> list[ColumnElement[bool]]:
        conditions: list[ColumnElement[bool]] = [DecisionLog.user_id == user_id]
        if target_type is not None:
            conditions.append(DecisionLog.target_type == target_type)
        if symbol is not None:
            conditions.append(DecisionLog.symbol == symbol)
        if decision_type is not None:
            conditions.append(DecisionLog.decision_type == decision_type)
        if status is not None:
            conditions.append(DecisionLog.status == status)
        if risk_type is not None:
            conditions.append(
                select(DecisionRisk.id)
                .where(
                    DecisionRisk.decision_id == DecisionLog.id,
                    DecisionRisk.risk_type == risk_type,
                )
                .exists()
            )
        if review_due_before is not None:
            conditions.append(cls._pending_date_review_at() <= review_due_before)
        return conditions
