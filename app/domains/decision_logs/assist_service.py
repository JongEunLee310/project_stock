import logging

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import DecisionAssistSnapshot
from app.adapters.llm.prompts.decision_assist import (
    build_decision_assist_system_prompt,
)
from app.adapters.llm.types import LLMTaskType
from app.domains.decision_logs.schema import (
    DecisionAssistRequest,
    DecisionAssistResponse,
    DecisionAssistResult,
)
from app.domains.decision_logs.types import TargetType


logger = logging.getLogger(__name__)


class DecisionAssistService:
    def __init__(self, gateway: LLMGateway) -> None:
        self.gateway = gateway

    def assist(
        self,
        user_id: int,
        data: DecisionAssistRequest,
    ) -> DecisionAssistResponse:
        snapshot = DecisionAssistSnapshot(
            target_type=data.target.type.value,
            symbol=(
                data.target.id if data.target.type is TargetType.SYMBOL else None
            ),
            decision_type=(
                data.decision_type.value if data.decision_type is not None else None
            ),
            thesis=data.thesis,
            rationale=data.rationale,
            memo=data.memo,
        )
        try:
            completion = self.gateway.complete_json(
                LLMTaskType.DECISION_ASSIST,
                snapshot,
                DecisionAssistResult,
                build_decision_assist_system_prompt(),
            )
            result = DecisionAssistResult.model_validate(completion.output)
        except Exception:
            logger.warning(
                "Decision assist failed; returning empty suggestions: user_id=%s",
                user_id,
                exc_info=True,
            )
            result = DecisionAssistResult()
        return DecisionAssistResponse.model_validate(result.model_dump())
