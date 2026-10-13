from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.agents.thesis_watch.model import ThesisCheck
from app.domains.agents.thesis_watch.schema import ThesisCheckCreate


class ThesisCheckRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, decision_id: int, check_date: date) -> ThesisCheck | None:
        return self.db.scalars(
            select(ThesisCheck).where(
                ThesisCheck.decision_id == decision_id,
                ThesisCheck.check_date == check_date,
            )
        ).first()

    def create(self, data: ThesisCheckCreate) -> ThesisCheck:
        check = ThesisCheck(**data.model_dump(mode="python"))
        self.db.add(check)
        self.db.flush()
        return check

    def list_by_user(self, user_id: int, limit: int) -> list[ThesisCheck]:
        return list(
            self.db.scalars(
                select(ThesisCheck)
                .where(ThesisCheck.user_id == user_id)
                .order_by(ThesisCheck.check_date.desc(), ThesisCheck.id.desc())
                .limit(limit)
            ).all()
        )
