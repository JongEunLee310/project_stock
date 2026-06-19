from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.alerts.model import Alert
from app.domains.alerts.schema import AlertCreate


class AlertRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_if_absent(self, data: AlertCreate) -> Alert | None:
        alert = Alert(
            user_id=data.user_id,
            signal_id=data.signal_id,
            dedup_key=data.dedup_key,
        )
        self.db.add(alert)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None
        self.db.refresh(alert)
        return alert

    def get_by_id(self, alert_id: int) -> Alert | None:
        return self.db.get(Alert, alert_id)

    def list_by_user(
        self,
        user_id: int,
        status: str | None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[Alert]:
        stmt = select(Alert).where(Alert.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        stmt = stmt.order_by(Alert.created_at.desc(), Alert.id.desc())
        stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self.db.scalars(stmt).all())

    def count_by_user(self, user_id: int, status: str | None) -> int:
        stmt = select(func.count()).select_from(Alert).where(Alert.user_id == user_id)
        if status is not None:
            stmt = stmt.where(Alert.status == status)
        return int(self.db.scalar(stmt) or 0)

    def update_status(self, alert: Alert, status: str) -> Alert:
        alert.status = status
        self.db.add(alert)
        self.db.commit()
        self.db.refresh(alert)
        return alert
