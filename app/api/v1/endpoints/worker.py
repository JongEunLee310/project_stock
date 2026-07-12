from pydantic import BaseModel, Field
from rq import Queue

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.v1.deps import get_current_user
from app.adapters.llm.types import LLMTaskType
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.response import ApiResponse, success
from app.domains.users.model import User
from app.scheduler.registry import default_scheduler_registry
from app.scheduler.runner import (
    ManualSchedulerRunner,
    SchedulerJobDisabledError,
    SchedulerJobNotFoundError,
)
from app.worker.connection import get_redis_connection
from app.worker.jobs.analysis import analyze_watchlist_job
from app.worker.jobs.earnings import collect_earnings_job
from app.worker.jobs.llm_analysis import run_llm_analysis_job
from app.worker.jobs.news import collect_news_job
from app.worker.jobs.valuation import collect_valuation_job

router = APIRouter()


class NewsJobRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class ValuationJobRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class EarningsJobRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class AnalysisJobRequest(BaseModel):
    watchlist_id: int


class SymbolRef(BaseModel):
    symbol: str
    market: str


class LLMAnalysisJobRequest(BaseModel):
    task_type: LLMTaskType
    symbols: list[SymbolRef] = Field(min_length=1)


class JobQueuedResponse(BaseModel):
    job_id: str
    status: str


class SchedulerJobRunResponse(BaseModel):
    job_name: str
    job_id: str
    status: str


def get_scheduler_runner() -> ManualSchedulerRunner:
    queue = Queue("default", connection=get_redis_connection())
    return ManualSchedulerRunner(default_scheduler_registry, queue)


@router.post(
    "/jobs/news",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue news collection job",
    description="Queue a background job that collects news for one or more asset symbols.",
)
def enqueue_news_job(payload: NewsJobRequest) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(collect_news_job, payload.symbols)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/jobs/valuation",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue valuation collection job",
    description="Queue a background job that collects valuation metrics for asset symbols.",
)
def enqueue_valuation_job(
    payload: ValuationJobRequest,
) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(collect_valuation_job, payload.symbols)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/jobs/earnings",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue earnings collection job",
    description="Queue a background job that collects quarterly earnings.",
)
def enqueue_earnings_job(
    payload: EarningsJobRequest,
) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(collect_earnings_job, payload.symbols)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/jobs/analysis",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue watchlist analysis job",
    description="Queue a background job that analyzes a watchlist and produces research artifacts.",
)
def enqueue_analysis_job(
    payload: AnalysisJobRequest,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[JobQueuedResponse]:
    connection = get_redis_connection()
    rate_limit_key = f"rate_limit:analysis_manual:{current_user.id}"
    if not connection.set(rate_limit_key, "1", nx=True, ex=60):
        raise AppException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="분석 요청은 60초에 한 번만 실행할 수 있습니다.",
            error_code=ErrorCode.RATE_LIMIT_EXCEEDED,
            headers={"Retry-After": "60"},
        )
    queue = Queue("default", connection=connection)
    job = queue.enqueue(analyze_watchlist_job, payload.watchlist_id)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/jobs/llm-analysis",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue LLM analysis job",
    description="Queue a background job that runs LLM analysis for the authenticated user.",
)
def enqueue_llm_analysis_job(
    payload: LLMAnalysisJobRequest,
    current_user: User = Depends(get_current_user),
) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(
        run_llm_analysis_job,
        current_user.id,
        payload.task_type.value,
        [(symbol.symbol, symbol.market) for symbol in payload.symbols],
    )
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/scheduler/jobs/{job_name}/run",
    response_model=ApiResponse[SchedulerJobRunResponse],
    summary="Run a registered scheduler job once",
    description="Execute one scheduler job immediately without registering a real periodic trigger.",
)
def run_scheduler_job_once(
    job_name: str,
    runner: ManualSchedulerRunner = Depends(get_scheduler_runner),
) -> ApiResponse[SchedulerJobRunResponse]:
    try:
        result = runner.run(job_name)
    except SchedulerJobNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="scheduler job not found",
        ) from exc
    except SchedulerJobDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="scheduler job is disabled",
        ) from exc
    return success(
        SchedulerJobRunResponse(
            job_name=result.job_name,
            job_id=result.job_id,
            status=result.status,
        )
    )
