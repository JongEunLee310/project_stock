from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import to_context_bundle_snapshot
from app.adapters.llm.prompts.analysis import (
    ANALYSIS_PROMPT_VERSION,
    build_analysis_system_prompt,
)
from app.adapters.llm.types import LLMTaskType
from app.domains.llm_analysis.model import LLMAnalysisRun
from app.domains.llm_analysis.repository import LLMAnalysisRunRepository
from app.domains.llm_analysis.schema import (
    LLMAnalysisResult,
    LLMAnalysisRunCreate,
    RunStatus,
)
from app.domains.llm_context.context_builder import ContextBuilder


class LLMAnalysisService:
    def __init__(
        self,
        db: Session,
        gateway: LLMGateway,
        context_builder: ContextBuilder | None = None,
    ) -> None:
        self.repository = LLMAnalysisRunRepository(db)
        self.gateway = gateway
        self.context_builder = context_builder or ContextBuilder(db)

    def run_analysis(
        self,
        task_type: LLMTaskType,
        user_id: int,
        symbols: list[tuple[str, str]],
    ) -> LLMAnalysisRun:
        bundle = self.context_builder.build_context_bundle(task_type, user_id, symbols)
        run = self.repository.create(
            LLMAnalysisRunCreate(
                user_id=user_id,
                task_type=task_type,
                related_symbols=[symbol for symbol, _market in symbols],
                input_context_json=bundle.model_dump(mode="json"),
                status=RunStatus.PENDING,
            )
        )

        try:
            output = self.gateway.complete_json(
                task_type,
                to_context_bundle_snapshot(bundle),
                LLMAnalysisResult,
                build_analysis_system_prompt(),
            )
            result = LLMAnalysisResult.model_validate(output)
        except Exception as exc:
            return self.repository.mark_failed(run.id, str(exc))

        return self.repository.mark_succeeded(
            run.id,
            output_json=result.model_dump(mode="json"),
            model_name=None,
            prompt_version=ANALYSIS_PROMPT_VERSION,
            provider=None,
        )
