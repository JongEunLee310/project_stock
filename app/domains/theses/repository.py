from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.theses.model import InvestmentThesis


class ThesisRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, thesis_id: int) -> InvestmentThesis | None:
        return self.db.get(InvestmentThesis, thesis_id)

    def get_latest_by_asset(
        self, asset_id: int, user_id: int
    ) -> InvestmentThesis | None:
        stmt = (
            select(InvestmentThesis)
            .where(
                InvestmentThesis.asset_id == asset_id,
                InvestmentThesis.user_id == user_id,
                InvestmentThesis.is_active.is_(True),
            )
            .order_by(InvestmentThesis.created_at.desc(), InvestmentThesis.id.desc())
        )
        return self.db.scalars(stmt).first()

    def list_by_asset(self, asset_id: int, user_id: int) -> list[InvestmentThesis]:
        stmt = (
            select(InvestmentThesis)
            .where(
                InvestmentThesis.asset_id == asset_id,
                InvestmentThesis.user_id == user_id,
            )
            .order_by(InvestmentThesis.created_at.desc(), InvestmentThesis.id.desc())
        )
        return list(self.db.scalars(stmt).all())

    def create(
        self,
        user_id: int,
        asset_id: int,
        summary: str,
        risk_factors: str | None,
        invalidation_conditions: str | None,
    ) -> InvestmentThesis:
        thesis = InvestmentThesis(
            user_id=user_id,
            asset_id=asset_id,
            summary=summary,
            risk_factors=risk_factors,
            invalidation_conditions=invalidation_conditions,
        )
        self.db.add(thesis)
        self.db.commit()
        self.db.refresh(thesis)
        return thesis

    def update(
        self,
        thesis_id: int,
        values: dict[str, str | None],
    ) -> InvestmentThesis | None:
        thesis = self.get_by_id(thesis_id)
        if thesis is None:
            return None
        for field, value in values.items():
            setattr(thesis, field, value)
        self.db.commit()
        self.db.refresh(thesis)
        return thesis

    def deactivate(self, thesis_id: int) -> InvestmentThesis | None:
        thesis = self.get_by_id(thesis_id)
        if thesis is None:
            return None
        thesis.is_active = False
        self.db.commit()
        self.db.refresh(thesis)
        return thesis
