from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.repository import AlertCandidateRepository
from app.domains.alert_candidates.schema import AlertCandidateCreate
from app.domains.alert_candidates.types import AlertCandidateStatus


class AlertCandidateService:
    def __init__(self, db: Session) -> None:
        self.repo = AlertCandidateRepository(db)

    def create_candidate(self, data: AlertCandidateCreate) -> AlertCandidate:
        return self.repo.create(data)

    def list_candidates(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
    ) -> list[AlertCandidate]:
        return self.repo.list_by_user(
            user_id,
            candidate_type=candidate_type,
            importance=importance,
            status=status,
            offset=offset,
            limit=limit,
            sort=sort,
        )

    def count_candidates(
        self,
        user_id: int,
        candidate_type: str | None = None,
        importance: str | None = None,
        status: str | None = None,
    ) -> int:
        return self.repo.count_by_user(
            user_id,
            candidate_type=candidate_type,
            importance=importance,
            status=status,
        )

    def mark_read(self, candidate_id: int, user_id: int) -> AlertCandidate:
        return self._update_owned_candidate(
            candidate_id,
            user_id,
            AlertCandidateStatus.READ.value,
        )

    def confirm(self, candidate_id: int, user_id: int) -> AlertCandidate:
        return self._update_owned_candidate(
            candidate_id,
            user_id,
            AlertCandidateStatus.CONFIRMED.value,
        )

    def _update_owned_candidate(
        self,
        candidate_id: int,
        user_id: int,
        status: str,
    ) -> AlertCandidate:
        candidate = self.repo.get_by_id(candidate_id)
        if candidate is None or candidate.user_id != user_id:
            raise AppException(
                status_code=404,
                detail="알림 후보를 찾을 수 없습니다.",
                error_code=ErrorCode.ALERT_CANDIDATE_NOT_FOUND,
            )
        return self.repo.update_status(candidate, status)
