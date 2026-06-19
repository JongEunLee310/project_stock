from fastapi import APIRouter

from app.api.v1.endpoints import (
    assets,
    auth,
    health,
    job_runs,
    reports,
    theses,
    watchlists,
    worker,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
api_router.include_router(theses.router, prefix="/theses", tags=["theses"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(job_runs.router, prefix="/job-runs", tags=["job-runs"])
api_router.include_router(worker.router, prefix="/worker", tags=["worker"])
