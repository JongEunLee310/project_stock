from sqlalchemy.orm import Session

from app.core.exceptions import AppException
from app.domains.alerts.model import Alert
from app.domains.alerts.repository import AlertRepository
from app.domains.alerts.schema import AlertCreate
from app.domains.alerts.types import AlertStatus
from app.domains.signals.model import Signal


class AlertService:
    def __init__(self, db: Session) -> None:
        self.repo = AlertRepository(db)

    def create_alert(self, user_id: int, signal: Signal) -> Alert | None:
        return self.repo.create_if_absent(
            AlertCreate(
                user_id=user_id,
                signal_id=signal.id,
                dedup_key=self._dedup_key(signal),
            )
        )

    def list_alerts(
        self,
        user_id: int,
        status: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Alert]:
        return self.repo.list_by_user(
            user_id,
            status,
            offset=offset,
            limit=limit,
        )

    def count_alerts(self, user_id: int, status: str | None = None) -> int:
        return self.repo.count_by_user(user_id, status)

    def mark_read(self, alert_id: int, user_id: int) -> Alert:
        return self._update_owned_alert(alert_id, user_id, AlertStatus.READ.value)

    def dismiss(self, alert_id: int, user_id: int) -> Alert:
        return self._update_owned_alert(alert_id, user_id, AlertStatus.DISMISSED.value)

    def _update_owned_alert(self, alert_id: int, user_id: int, status: str) -> Alert:
        alert = self.repo.get_by_id(alert_id)
        if alert is None or alert.user_id != user_id:
            raise AppException(status_code=404, detail="알림을 찾을 수 없습니다.")
        return self.repo.update_status(alert, status)

    def _dedup_key(self, signal: Signal) -> str:
        if signal.news_item_id is not None:
            return f"{signal.signal_type}:{signal.news_item_id}"
        return f"{signal.signal_type}:signal:{signal.id}"
