from app.adapters.factory import get_llm_gateway
from app.adapters.llm.types import LLMTaskType
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.llm_analysis.schema import RunStatus
from app.domains.llm_analysis.service import LLMAnalysisService


def run_llm_analysis_job(
    user_id: int,
    task_type: str,
    symbols: list[tuple[str, str]],
) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        job_run = job_run_service.start(
            "llm_analysis",
            {
                "user_id": user_id,
                "task_type": task_type,
                "symbols": symbols,
            },
        )
        job_run_id = job_run.id
        run = LLMAnalysisService(db, get_llm_gateway()).run_analysis(
            LLMTaskType(task_type),
            user_id,
            symbols,
        )
        if run.status == RunStatus.SUCCEEDED.value:
            job_run_service.succeed(job_run.id)
            return None
        job_run_service.fail(
            job_run.id,
            run.error_message or "LLM analysis failed",
        )
        return None
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
