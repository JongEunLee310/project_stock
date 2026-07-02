from app.adapters.factory import get_price_series_provider
from app.db.session import SessionLocal
from app.domains.jobs.service import JobRunService
from app.domains.prices.ingestion_service import PriceIngestionService
from app.domains.prices.universe import PriceUniverseResolver


def collect_prices_job(symbols: list[str] | None = None) -> None:
    db = SessionLocal()
    job_run_service = JobRunService(db)
    job_run_id: int | None = None
    targets: list[tuple[str, str]] = []
    try:
        if symbols is None:
            targets = PriceUniverseResolver(db).resolve()
        else:
            targets = [(symbol.upper(), "NASDAQ") for symbol in symbols]
        job_run = job_run_service.start(
            "price_collection",
            {"targets": [{"symbol": symbol, "market": market} for symbol, market in targets]},
        )
        job_run_id = job_run.id
        PriceIngestionService(db).collect_and_save(
            get_price_series_provider(),
            targets,
        )
        job_run_service.succeed(job_run.id)
        return None
    except Exception as exc:
        if job_run_id is not None:
            job_run_service.fail(job_run_id, str(exc))
        raise
    finally:
        db.close()
