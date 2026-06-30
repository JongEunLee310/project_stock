from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import to_dashboard_snapshot
from app.adapters.llm.prompts.dashboard_briefing import DASHBOARD_BRIEFING_SYSTEM_PROMPT
from app.adapters.llm.schema import BriefingResult
from app.adapters.llm.types import LLMTaskType
from app.domains.dashboard.schema import DashboardBriefingResponse
from app.domains.dashboard.service import DashboardService
from app.domains.signals.time import utc_now


class DashboardBriefingService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.dashboard_service = DashboardService(db)
        self.gateway = gateway

    def generate(self, user_id: int) -> DashboardBriefingResponse:
        summary = self.dashboard_service.get_summary(user_id)
        snapshot = to_dashboard_snapshot(summary, highlights=[])
        result = BriefingResult.model_validate(
            self.gateway.complete_json(
                LLMTaskType.DASHBOARD_BRIEFING,
                snapshot,
                BriefingResult,
                DASHBOARD_BRIEFING_SYSTEM_PROMPT,
            )
        )
        return DashboardBriefingResponse(
            **result.model_dump(),
            generated_at=utc_now(),
        )
