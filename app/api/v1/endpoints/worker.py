from pydantic import BaseModel, Field
from rq import Queue

from fastapi import APIRouter

from app.core.response import ApiResponse, success
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


@router.post("/jobs/news", response_model=ApiResponse[JobQueuedResponse])
def enqueue_news_job(payload: NewsJobRequest) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(collect_news_job, payload.symbols)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))


@router.post("/jobs/analysis", response_model=ApiResponse[JobQueuedResponse])
def enqueue_analysis_job(payload: AnalysisJobRequest) -> ApiResponse[JobQueuedResponse]:
    queue = Queue("default", connection=get_redis_connection())
    job = queue.enqueue(analyze_watchlist_job, payload.watchlist_id)
    return success(JobQueuedResponse(job_id=str(job.id), status="queued"))
