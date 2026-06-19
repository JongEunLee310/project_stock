from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.theses.conflict_model import ThesisConflictAnalysis
from app.domains.theses.conflict_schema import ThesisConflictResult


class ThesisConflictRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        news_item_id: int,
        thesis_id: int,
        result: ThesisConflictResult,
    ) -> ThesisConflictAnalysis:
        analysis = ThesisConflictAnalysis(
            news_item_id=news_item_id,
            thesis_id=thesis_id,
            status=result.status,
            reason=result.reason,
            invalidation_triggered=result.invalidation_triggered,
        )
        self.db.add(analysis)
        self.db.commit()
        self.db.refresh(analysis)
        return analysis

    def get_by_news_and_thesis(
        self, news_item_id: int, thesis_id: int
    ) -> list[ThesisConflictAnalysis]:
        stmt = (
            select(ThesisConflictAnalysis)
            .where(
                ThesisConflictAnalysis.news_item_id == news_item_id,
                ThesisConflictAnalysis.thesis_id == thesis_id,
            )
            .order_by(
                ThesisConflictAnalysis.created_at.desc(),
                ThesisConflictAnalysis.id.desc(),
            )
        )
        return list(self.db.scalars(stmt).all())
