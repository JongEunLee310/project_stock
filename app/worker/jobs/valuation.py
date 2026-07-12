from app.adapters.factory import get_valuation_provider
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.prices.universe import PriceUniverseResolver
from app.domains.valuation.ingestion_service import ValuationIngestionService


def collect_valuation_job(symbols: list[str] | None = None) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    try:
        targets = (
            PriceUniverseResolver(db).resolve_assets()
            if symbols is None
            else [(symbol.upper(), "NASDAQ") for symbol in symbols]
        )
        job_run = job_run_service.start(
            "valuation_collection",
            {"targets": [{"symbol": symbol, "market": market} for symbol, market in targets]},
        )
        job_run_id = job_run.id
        ValuationIngestionService(db).collect_and_save(
            get_valuation_provider(), targets
        )
        job_run_service.succeed(job_run.id)
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
