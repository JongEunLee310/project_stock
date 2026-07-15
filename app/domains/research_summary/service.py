from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import to_research_summary_snapshot
from app.adapters.llm.prompts.research_summary import RESEARCH_SUMMARY_SYSTEM_PROMPT
from app.adapters.llm.schema import ResearchSummaryResult
from app.adapters.llm.types import LLMTaskType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.assets.model import Asset
from app.domains.assets.repository import AssetRepository
from app.domains.llm_context.context_builder import ContextBuilder
from app.domains.research_summary.model import ResearchSummaryRow
from app.domains.research_summary.repository import ResearchSummaryRepository
from app.domains.research_summary.schema import (
    CounterPoint,
    ResearchRisk,
    ResearchSummaryResponse,
)


class ResearchSummaryService:
    def __init__(
        self,
        db: Session,
        gateway: LLMGateway,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.asset_repo = AssetRepository(db)
        self.repository = ResearchSummaryRepository(db)
        self.gateway = gateway
        self.context_builder = context_builder or ContextBuilder(db)
        self._prefetched_rows: dict[int, ResearchSummaryRow] | None = None

    def get_summary(self, asset_id: int) -> ResearchSummaryResponse:
        self._get_asset(asset_id)
        row = self.repository.get_by_asset_id(asset_id)
        if row is None:
            raise AppException(
                status_code=404,
                detail="저장된 리서치 요약을 찾을 수 없습니다.",
                error_code=ErrorCode.RESEARCH_SUMMARY_NOT_FOUND,
            )
        return self._to_response(row)

    def prefetch(self, asset_ids: list[int]) -> None:
        self._prefetched_rows = {
            row.asset_id: row for row in self.repository.get_by_asset_ids(asset_ids)
        }

    def get_summary_or_none(self, asset_id: int) -> ResearchSummaryResponse | None:
        row = (
            self._prefetched_rows.get(asset_id)
            if self._prefetched_rows is not None
            else self.repository.get_by_asset_id(asset_id)
        )
        return self._to_response(row) if row is not None else None

    def generate(self, asset_id: int, user_id: int) -> ResearchSummaryResponse:
        asset = self._get_asset(asset_id)
        card = self.context_builder.build_symbol_context(
            user_id,
            asset.symbol,
            asset.market,
        )
        snapshot = to_research_summary_snapshot(card)
        result = ResearchSummaryResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.RESEARCH_SUMMARY,
                snapshot,
                ResearchSummaryResult,
                RESEARCH_SUMMARY_SYSTEM_PROMPT,
            ).output
        )
        return self._to_response(self.repository.upsert(asset.id, result))

    def _get_asset(self, asset_id: int) -> Asset:
        asset = self.asset_repo.get_by_id(asset_id)
        if asset is None:
            raise AppException(
                status_code=404,
                detail="종목을 찾을 수 없습니다.",
                error_code=ErrorCode.ASSET_NOT_FOUND,
            )
        return asset

    @staticmethod
    def _to_response(row: ResearchSummaryRow) -> ResearchSummaryResponse:
        # 기존 응답 필드명은 created_at이지만 실제 의미는 마지막 생성 시각이다.
        return ResearchSummaryResponse(
            asset_id=row.asset_id,
            stance=row.stance,
            stance_confidence=row.stance_confidence,
            stance_comment=row.stance_comment,
            headline=row.headline,
            body=row.body,
            positive_factors=row.positive_factors,
            caution_factors=row.caution_factors,
            next_checks=row.next_checks,
            counter_points=[
                CounterPoint.model_validate(point) for point in row.counter_points
            ],
            confidence_basis=row.confidence_basis,
            key_risks=[ResearchRisk.model_validate(risk) for risk in row.key_risks],
            created_at=row.updated_at,
        )
