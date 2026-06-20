from pydantic import BaseModel, Field
from rq import Queue
from sqlalchemy.orm import Session

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.response import ApiResponse, success
from app.db.session import get_db
from app.domains.jobs.service import JobRunService
from app.scheduler.registry import default_scheduler_registry
from app.scheduler.runner import (
    ManualSchedulerRunner,
    SchedulerJobDisabledError,
    SchedulerJobNotFoundError,
)
from app.worker.connection import get_redis_connection
from app.worker.jobs.analysis import analyze_watchlist_job
from app.worker.jobs.news import collect_news_job

router = APIRouter()


class NewsJobRequest(BaseModel):
    symbols: list[str] = Field(min_length=1)


class AnalysisJobRequest(BaseModel):
    watchlist_id: int


class JobQueuedResponse(BaseModel):
    job_id: str
    status: str


class SchedulerJobRunResponse(BaseModel):
    job_name: str
    job_run_id: int
    status: str


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
    "/jobs/analysis",
    response_model=ApiResponse[JobQueuedResponse],
    summary="Enqueue watchlist analysis job",
    description="Queue a background job that analyzes a watchlist and produces research artifacts.",
)
def enqueue_analysis_job(payload: AnalysisJobRequest) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(analyze_watchlist_job, payload.watchlist_id)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post(
    "/scheduler/jobs/{job_name}/run",
    response_model=ApiResponse[SchedulerJobRunResponse],
    summary="Run a registered scheduler job once",
    description="Execute one scheduler job immediately without registering a real periodic trigger.",
)
def run_scheduler_job_once(
    job_name: str,
    db: Session = Depends(get_db),
) -> ApiResponse[SchedulerJobRunResponse]:
    runner = ManualSchedulerRunner(
        default_scheduler_registry,
        JobRunService(db),
    )
    try:
        result = runner.run_once(job_name)
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
            job_run_id=result.job_run_id,
            status=result.status,
        )
    )
