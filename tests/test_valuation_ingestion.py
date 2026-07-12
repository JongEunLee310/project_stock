from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import ValuationProvider, ValuationResult
from app.adapters.market.yfinance import valuation_from_info
from app.domains.assets.model import Asset
from app.domains.jobs.model import JobRun
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.domains.valuation.ingestion_service import ValuationIngestionService
from app.domains.valuation.model import ValuationSnapshot
from app.worker.jobs import valuation
from app.worker.jobs.valuation import collect_valuation_job


def valuation_result(*, per: str = "18.3") -> ValuationResult:
    return ValuationResult(
        # Source: docs/designs/279-valuation-real-collection.md mapping fixture.
        per=Decimal(per),
        forward_per=Decimal("16.9"),
        psr=Decimal("2.4"),
        pbr=Decimal("3.1"),
        ev_ebitda=Decimal("11.7"),
        peg=Decimal("1.2"),
        fcf_yield=Decimal("5.4"),
        as_of=date(2026, 7, 12),
        source="fixture",
    )


class StaticValuationProvider(ValuationProvider):
    def __init__(
        self, results: dict[str, ValuationResult | Exception | None]
    ) -> None:
        self.results = results

    def get_valuation(self, symbol: str, market: str) -> ValuationResult | None:
        result = self.results.get(symbol)
        if isinstance(result, Exception):
            raise result
        return result


def test_ingestion_upserts_same_as_of_snapshot(db: Session) -> None:
    service = ValuationIngestionService(db)
    targets = [("aapl", "nasdaq")]

    first = service.collect_and_save(
        StaticValuationProvider({"AAPL": valuation_result(per="18.3")}), targets
    )
    second = service.collect_and_save(
        StaticValuationProvider({"AAPL": valuation_result(per="20.1")}), targets
    )

    assert first.saved_count == 1
    assert second.saved_count == 1
    assert db.scalar(select(func.count()).select_from(ValuationSnapshot)) == 1
    snapshot = db.scalars(select(ValuationSnapshot)).one()
    assert snapshot.per == Decimal("20.1000")
    assert (snapshot.symbol, snapshot.market) == ("AAPL", "NASDAQ")


def test_ingestion_skips_unavailable_and_failed_targets(db: Session) -> None:
    result = ValuationIngestionService(db).collect_and_save(
        StaticValuationProvider(
            {
                "AAPL": valuation_result(),
                "MISSING": None,
                "FAILED": RuntimeError("provider unavailable"),
            }
        ),
        [("MISSING", "NYSE"), ("FAILED", "NASDAQ"), ("AAPL", "NASDAQ")],
    )

    assert result.target_count == 3
    assert result.success_count == 1
    assert result.failure_count == 2
    assert result.saved_count == 1


def test_yfinance_info_mapping_is_pure_and_handles_missing_values() -> None:
    result = valuation_from_info(
        {
            "trailingPE": 18.3,
            "forwardPE": float("nan"),
            "priceToSalesTrailing12Months": 2.4,
            "priceToBook": 3.1,
            "enterpriseToEbitda": 11.7,
            "trailingPegRatio": 1.2,
            "freeCashflow": 54,
            "marketCap": 1000,
        },
        as_of=date(2026, 7, 12),
        source="yfinance",
    )

    assert result == ValuationResult(
        per=Decimal("18.3"),
        forward_per=None,
        psr=Decimal("2.4"),
        pbr=Decimal("3.1"),
        ev_ebitda=Decimal("11.7"),
        peg=Decimal("1.2"),
        fcf_yield=Decimal("5.400"),
        as_of=date(2026, 7, 12),
        source="yfinance",
    )


def test_collect_valuation_job_uses_asset_universe_and_records_success(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    watchlist = Watchlist(user_id=1, name="Main")
    db.add_all([asset, watchlist])
    db.commit()
    db.refresh(asset)
    db.refresh(watchlist)
    db.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    db.commit()
    monkeypatch.setattr(valuation, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        valuation,
        "get_valuation_provider",
        lambda: StaticValuationProvider({"AAPL": valuation_result()}),
    )

    collect_valuation_job()

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "valuation_collection"
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "targets": [{"symbol": "AAPL", "market": "NASDAQ"}]
    }
    assert db.scalars(select(ValuationSnapshot)).one().symbol == "AAPL"
