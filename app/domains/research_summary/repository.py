from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm.schema import ResearchSummaryResult
from app.domains.research_summary.model import ResearchSummaryRow


class ResearchSummaryRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_asset_id(self, asset_id: int) -> ResearchSummaryRow | None:
        return self.db.scalars(
            select(ResearchSummaryRow).where(ResearchSummaryRow.asset_id == asset_id)
        ).first()

    def get_by_asset_ids(self, asset_ids: list[int]) -> list[ResearchSummaryRow]:
        if not asset_ids:
            return []
        return list(
            self.db.scalars(
                select(ResearchSummaryRow).where(
                    ResearchSummaryRow.asset_id.in_(asset_ids)
                )
            )
        )

    def upsert(
        self,
        asset_id: int,
        result: ResearchSummaryResult,
    ) -> ResearchSummaryRow:
        row = self.get_by_asset_id(asset_id)
        values = {
            "stance": result.stance,
            "stance_confidence": result.stance_confidence,
            "stance_comment": result.stance_comment,
            "headline": result.headline,
            "body": result.body,
            "positive_factors": list(result.positive_factors),
            "caution_factors": list(result.caution_factors),
            "next_checks": list(result.next_checks),
            "counter_points": [
                point.model_dump(mode="json") for point in result.counter_points
            ],
            "confidence_basis": result.confidence_basis,
            "key_risks": [risk.model_dump(mode="json") for risk in result.key_risks],
        }
        if row is None:
            row = ResearchSummaryRow(asset_id=asset_id, **values)
            self.db.add(row)
        else:
            for field, value in values.items():
                setattr(row, field, value)
        self.db.commit()
        self.db.refresh(row)
        return row
