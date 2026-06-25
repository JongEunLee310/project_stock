from fastapi import APIRouter

from app.api.v1.endpoints import (
    alert_candidates,
    alerts,
    assets,
    auth,
    dashboard,
    health,
    job_runs,
    portfolios,
    prices,
    reports,
    signals,
    theses,
    watchlists,
    worker,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(
    alert_candidates.router,
    prefix="/alert-candidates",
    tags=["alert-candidates"],
)
api_router.include_router(alerts.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(assets.router, prefix="/assets", tags=["assets"])
api_router.include_router(prices.router, prefix="/stocks", tags=["prices"])
api_router.include_router(watchlists.router, prefix="/watchlists", tags=["watchlists"])
api_router.include_router(portfolios.router, prefix="/portfolios", tags=["portfolios"])
api_router.include_router(theses.router, prefix="/theses", tags=["theses"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(signals.router, prefix="/signals", tags=["signals"])
api_router.include_router(job_runs.router, prefix="/job-runs", tags=["job-runs"])
api_router.include_router(worker.router, prefix="/worker", tags=["worker"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
