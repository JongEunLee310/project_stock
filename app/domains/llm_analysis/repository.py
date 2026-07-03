from typing import Any

from sqlalchemy.orm import Session

from app.domains.llm_analysis.model import LLMAnalysisRun
from app.domains.llm_analysis.schema import LLMAnalysisRunCreate, RunStatus


class LLMAnalysisRunRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(self, data: LLMAnalysisRunCreate) -> LLMAnalysisRun:
        run = LLMAnalysisRun(
            user_id=data.user_id,
            task_type=data.task_type.value,
            related_symbols=data.related_symbols,
            input_context_json=data.input_context_json,
            output_json=data.output_json,
            status=data.status.value,
            model_name=data.model_name,
            prompt_version=data.prompt_version,
            provider=data.provider,
            related_decision_log_id=data.related_decision_log_id,
            error_message=data.error_message,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def get_by_id(self, run_id: int) -> LLMAnalysisRun | None:
        return self.db.get(LLMAnalysisRun, run_id)

    def mark_succeeded(
        self,
        run_id: int,
        output_json: dict[str, Any],
        model_name: str | None,
        prompt_version: str,
        provider: str | None,
    ) -> LLMAnalysisRun:
        run = self._get_required(run_id)
        run.output_json = output_json
        run.status = RunStatus.SUCCEEDED.value
        run.model_name = model_name
        run.prompt_version = prompt_version
        run.provider = provider
        run.error_message = None
        self.db.commit()
        self.db.refresh(run)
        return run

    def mark_failed(self, run_id: int, error_message: str) -> LLMAnalysisRun:
        run = self._get_required(run_id)
        run.status = RunStatus.FAILED.value
        run.error_message = error_message
        self.db.commit()
        self.db.refresh(run)
        return run

    def _get_required(self, run_id: int) -> LLMAnalysisRun:
        run = self.get_by_id(run_id)
        if run is None:
            raise ValueError(f"LLM analysis run not found: {run_id}")
        return run
