from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.schema import AlertCandidateCreate


class AlertCandidateRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: AlertCandidateCreate) -> AlertCandidate:
        candidate = AlertCandidate(
            user_id=data.user_id,
            candidate_type=data.candidate_type,
            importance=data.importance,
            title=data.title,
            message=data.message,
            asset_id=data.asset_id,
            evidence=data.evidence,
        )
        self.db.add(candidate)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    def get_by_id(self, candidate_id: int) -> AlertCandidate | None:
        return self.db.get(AlertCandidate, candidate_id)

    def list_by_user(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[AlertCandidate]:
        stmt = self._filtered_query(user_id, candidate_type, importance, status)
        stmt = stmt.order_by(AlertCandidate.created_at.desc(), AlertCandidate.id.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
    ) -> int:
        stmt = (
            select(func.count())
            .select_from(AlertCandidate)
            .where(AlertCandidate.user_id == user_id)
        )
        if candidate_type is not None:
            stmt = stmt.where(AlertCandidate.candidate_type == candidate_type)
        if importance is not None:
            stmt = stmt.where(AlertCandidate.importance == importance)
        if status is not None:
            stmt = stmt.where(AlertCandidate.status == status)
        return int(self.db.scalar(stmt) or 0)

    def update_status(
        self,
        candidate: AlertCandidate,
        status: str,
    ) -> AlertCandidate:
        candidate.status = status
        self.db.add(candidate)
        self.db.commit()
        self.db.refresh(candidate)
        return candidate

    def _filtered_query(
        self,
        user_id: int,
        candidate_type: str | None,
        importance: str | None,
        status: str | None,
    ) -> Select[tuple[AlertCandidate]]:
        stmt = select(AlertCandidate).where(AlertCandidate.user_id == user_id)
        if candidate_type is not None:
            stmt = stmt.where(AlertCandidate.candidate_type == candidate_type)
        if importance is not None:
            stmt = stmt.where(AlertCandidate.importance == importance)
        if status is not None:
            stmt = stmt.where(AlertCandidate.status == status)
        return stmt
