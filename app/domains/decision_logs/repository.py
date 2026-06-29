from enum import Enum

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domains.decision_logs.model import DecisionLog
from app.domains.decision_logs.schema import DecisionLogCreate, DecisionLogUpdate


class DecisionLogRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, decision_log_id: int) -> DecisionLog | None:
        return self.db.get(DecisionLog, decision_log_id)

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
            .where(
                DecisionLog.user_id == user_id,
            )
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

    def create(self, user_id: int, data: DecisionLogCreate) -> DecisionLog:
        values = data.model_dump()
        values["decision_type"] = data.decision_type.value
        values["decision_status"] = data.decision_status.value
        values["created_by"] = data.created_by.value
        decision_log = DecisionLog(user_id=user_id, **values)
        self.db.add(decision_log)
        self.db.commit()
        self.db.refresh(decision_log)
        return decision_log

    def update(self, decision_log: DecisionLog, data: DecisionLogUpdate) -> DecisionLog:
        values = data.model_dump(exclude_unset=True)
        for enum_field in ("decision_type", "decision_status", "created_by"):
            if isinstance(values.get(enum_field), Enum):
                values[enum_field] = values[enum_field].value
        for field, value in values.items():
            setattr(decision_log, field, value)
        self.db.commit()
        self.db.refresh(decision_log)
        return decision_log

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
