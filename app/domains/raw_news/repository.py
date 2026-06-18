from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.raw_news.model import RawNewsEvent
from app.domains.raw_news.schema import RawNewsEventCreate


class RawNewsEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_or_skip(self, data: RawNewsEventCreate) -> RawNewsEvent | None:
        values = data.model_dump(exclude_none=True)
        event = RawNewsEvent(**values)
        self.db.add(event)
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()
            return None
        self.db.refresh(event)
        return event

    def get_by_url(self, url: str) -> RawNewsEvent | None:
        stmt = select(RawNewsEvent).where(RawNewsEvent.url == url)
        return self.db.scalars(stmt).first()
