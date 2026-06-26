from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.decision_logs.model import DecisionLog
from app.domains.decision_logs.repository import DecisionLogRepository
from app.domains.decision_logs.schema import (
    DecisionLogCreate,
    DecisionLogResponse,
    DecisionLogUpdate,
)
from app.domains.decision_logs.types import DecisionStatus


class DecisionLogService:
    def __init__(self, db: Session) -> None:
        self.repo = DecisionLogRepository(db)

    def create_decision_log(
        self,
        user_id: int,
        data: DecisionLogCreate,
    ) -> DecisionLogResponse:
        if data.decided_at is None:
            data = data.model_copy(update={"decided_at": self._now()})
        decision_log = self.repo.create(user_id=user_id, data=data)
        return DecisionLogResponse.model_validate(decision_log)

    def list_decision_logs(
        self,
        user_id: int,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-decided_at",
    ) -> list[DecisionLogResponse]:
        return [
            DecisionLogResponse.model_validate(decision_log)
            for decision_log in self.repo.list_by_user(
                user_id,
                offset=offset,
                limit=limit,
                sort=sort,
            )
        ]

    def count_decision_logs(self, user_id: int) -> int:
        return self.repo.count_by_user(user_id)

    def get_decision_log(
        self,
        decision_log_id: int,
        user_id: int,
    ) -> DecisionLogResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        return DecisionLogResponse.model_validate(decision_log)

    def update_decision_log(
        self,
        decision_log_id: int,
        user_id: int,
        data: DecisionLogUpdate,
    ) -> DecisionLogResponse:
        decision_log = self._get_owned_decision_log(decision_log_id, user_id)
        update_data = self._with_lifecycle_stamp(decision_log, data)
        updated_decision_log = self.repo.update(decision_log, update_data)
        return DecisionLogResponse.model_validate(updated_decision_log)

    def _get_owned_decision_log(
        self,
        decision_log_id: int,
        user_id: int,
    ) -> DecisionLog:
        decision_log = self.repo.get_by_id(decision_log_id)
        if decision_log is None:
            raise AppException(
                status_code=404,
                detail="의사결정 기록을 찾을 수 없습니다.",
                error_code=ErrorCode.DECISION_LOG_NOT_FOUND,
            )
        if decision_log.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="의사결정 기록 접근 권한이 없습니다.",
                error_code=ErrorCode.DECISION_LOG_FORBIDDEN,
            )
        return decision_log

    def _with_lifecycle_stamp(
        self,
        decision_log: DecisionLog,
        data: DecisionLogUpdate,
    ) -> DecisionLogUpdate:
        values = data.model_dump(exclude_unset=True)
        if data.decision_status == DecisionStatus.REVIEWED:
            if "reviewed_at" not in values and decision_log.reviewed_at is None:
                values["reviewed_at"] = self._now()
        if data.decision_status == DecisionStatus.CLOSED:
            if "closed_at" not in values and decision_log.closed_at is None:
                values["closed_at"] = self._now()
        if not values:
            return data
        return data.model_copy(update=values)

    def _now(self) -> datetime:
        return datetime.now(UTC)
