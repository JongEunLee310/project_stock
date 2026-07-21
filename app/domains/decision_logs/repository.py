from datetime import UTC, datetime
from enum import Enum

from sqlalchemy import Select, func, select
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
from app.domains.decision_logs.types import DecisionStatus, ReviewTriggerStatus


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
        sort: str = "-decided_at",
    ) -> list[DecisionLog]:
        stmt = select(DecisionLog).where(DecisionLog.user_id == user_id)
        stmt = self._apply_sort(stmt, sort).offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(DecisionLog)
            .where(DecisionLog.user_id == user_id)
        )
        return int(self.db.scalar(stmt) or 0)

    def count_by_decision_type(self, user_id: int) -> dict[str, int]:
        stmt = (
            select(DecisionLog.decision_type, func.count())
            .where(DecisionLog.user_id == user_id)
            .group_by(DecisionLog.decision_type)
        )
        return {
            str(decision_type): int(count)
            for decision_type, count in self.db.execute(stmt).all()
        }

    def list_recent_reviewed(self, user_id: int, limit: int) -> list[DecisionLog]:
        stmt = (
            select(DecisionLog)
            .where(
                DecisionLog.user_id == user_id,
                DecisionLog.reviewed_at.is_not(None),
            )
            .order_by(DecisionLog.reviewed_at.desc(), DecisionLog.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

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
