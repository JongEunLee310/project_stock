from datetime import date, datetime
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.market.base import (
    EarningsEventResult,
    EarningsProvider,
    EarningsReportResult,
)
from app.adapters.market.yfinance import (
    earnings_events_from_frame,
    earnings_reports_from_frames,
    period_from_end,
)
from app.domains.assets.model import Asset
from app.domains.earnings.ingestion_service import EarningsIngestionService
from app.domains.earnings.model import EarningsEvent, EarningsReport
from app.domains.jobs.model import JobRun
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.worker.jobs import earnings
from app.worker.jobs.earnings import collect_earnings_job


def report(*, revenue: str = "100") -> EarningsReportResult:
    return EarningsReportResult(
        # Source: docs/designs/280-earnings-real-collection.md mapping fixture.
        period_end=date(2025, 12, 31),
        revenue=Decimal(revenue),
        operating_income=Decimal("25"),
        eps=Decimal("1.2"),
        eps_estimate=Decimal("1.1"),
        source="fixture",
    )


def event(*, actual: str | None = "1.2") -> EarningsEventResult:
    return EarningsEventResult(
        # Source: docs/designs/282-earnings-event-history.md mapping fixture.
        event_date=date(2026, 1, 25),
        eps_actual=Decimal(actual) if actual is not None else None,
        eps_estimate=Decimal("1.1"),
        source="fixture",
    )


class StaticEarningsProvider(EarningsProvider):
    def __init__(
        self,
        results: dict[str, list[EarningsReportResult] | Exception],
        events: dict[str, list[EarningsEventResult] | Exception] | None = None,
    ) -> None:
        self.results = results
        self.events = events or {
            symbol: [event()] for symbol, result in results.items() if not isinstance(result, Exception)
        }

    def get_quarterly_earnings(
        self, symbol: str, market: str
    ) -> list[EarningsReportResult]:
        result = self.results.get(symbol, [])
        if isinstance(result, Exception):
            raise result
        return result

    def get_earnings_events(
        self, symbol: str, market: str
    ) -> list[EarningsEventResult]:
        result = self.events.get(symbol, [])
        if isinstance(result, Exception):
            raise result
        return result


def test_ingestion_upserts_same_period(db: Session) -> None:
    service = EarningsIngestionService(db)
    first = service.collect_and_save(
        StaticEarningsProvider({"AAPL": [report(revenue="100")]}),
        [("aapl", "nasdaq")],
    )
    second = service.collect_and_save(
        StaticEarningsProvider({"AAPL": [report(revenue="120")]}),
        [("aapl", "nasdaq")],
    )
    assert first.saved_count == second.saved_count == 2
    assert db.scalar(select(func.count()).select_from(EarningsReport)) == 1
    saved = db.scalars(select(EarningsReport)).one()
    assert saved.revenue == Decimal("120.0000")
    assert (saved.symbol, saved.market, saved.period) == (
        "AAPL", "NASDAQ", "2025Q4"
    )


def test_ingestion_upserts_same_event_date(db: Session) -> None:
    service = EarningsIngestionService(db)

    first = service.collect_and_save(
        StaticEarningsProvider(
            {"AAPL": [report()]},
            {"AAPL": [event(actual="1.2")]},
        ),
        [("aapl", "nasdaq")],
    )
    second = service.collect_and_save(
        StaticEarningsProvider(
            {"AAPL": [report()]},
            {"AAPL": [event(actual="1.4")]},
        ),
        [("aapl", "nasdaq")],
    )

    assert first.saved_count == second.saved_count == 2
    assert db.scalar(select(func.count()).select_from(EarningsEvent)) == 1
    saved = db.scalars(select(EarningsEvent)).one()
    # Source: event fixtures immediately above.
    assert saved.eps_actual == Decimal("1.4000")
    assert (saved.symbol, saved.market, saved.event_date) == (
        "AAPL",
        "NASDAQ",
        date(2026, 1, 25),
    )


def test_ingestion_skips_empty_and_failed_targets(db: Session) -> None:
    result = EarningsIngestionService(db).collect_and_save(
        StaticEarningsProvider({
            "AAPL": [report()],
            "FAILED": RuntimeError("provider unavailable"),
        }),
        [("MISSING", "NYSE"), ("FAILED", "NASDAQ"), ("AAPL", "NASDAQ")],
    )
    assert result.target_count == 3
    assert result.success_count == 1
    assert result.failure_count == 2
    assert result.saved_count == 2
    assert result.report_success_count == 1
    assert result.report_failure_count == 2
    assert result.event_success_count == 1
    assert result.event_failure_count == 0


def test_ingestion_counts_event_collection_failure(db: Session) -> None:
    result = EarningsIngestionService(db).collect_and_save(
        StaticEarningsProvider(
            {"AAPL": [report()]},
            {"AAPL": RuntimeError("event provider unavailable")},
        ),
        [("AAPL", "NASDAQ")],
    )

    assert result.success_count == 0
    assert result.failure_count == 1
    assert result.report_success_count == 1
    assert result.report_failure_count == 0
    assert result.event_success_count == 0
    assert result.event_failure_count == 1
    assert db.scalar(select(func.count()).select_from(EarningsEvent)) == 0


def test_ingestion_counts_empty_events_separately(db: Session) -> None:
    result = EarningsIngestionService(db).collect_and_save(
        StaticEarningsProvider({"AAPL": [report()]}, {"AAPL": []}),
        [("AAPL", "NASDAQ")],
    )

    assert result.success_count == 0
    assert result.failure_count == 1
    assert result.report_success_count == 1
    assert result.event_failure_count == 1
    assert db.scalar(select(func.count()).select_from(EarningsReport)) == 1


def test_yfinance_mapping_handles_missing_rows_and_matches_estimates() -> None:
    income = pd.DataFrame(
        {
            datetime(2025, 12, 31): [Decimal("125"), Decimal("1.20")],
            datetime(2025, 9, 30): [Decimal("108"), Decimal("0.90")],
        },
        index=["Total Revenue", "Diluted EPS"],
    )
    earnings_dates = pd.DataFrame(
        {"EPS Estimate": [Decimal("1.10"), Decimal("1.00")]},
        index=[datetime(2026, 1, 25), datetime(2025, 10, 20)],
    )
    results = earnings_reports_from_frames(income, earnings_dates, source="fixture")
    # Source: DataFrame fixture immediately above.
    assert [item.period_end for item in results] == [
        date(2025, 12, 31), date(2025, 9, 30)
    ]
    assert [item.revenue for item in results] == [Decimal("125"), Decimal("108")]
    assert [item.operating_income for item in results] == [None, None]
    assert [item.eps_estimate for item in results] == [
        Decimal("1.10"), Decimal("1.00")
    ]
    assert period_from_end(results[0].period_end) == "2025Q4"


def test_yfinance_event_mapping_handles_nulls_and_deduplicates_dates() -> None:
    earnings_dates = pd.DataFrame(
        {
            "Reported EPS": [Decimal("1.20"), Decimal("9.99"), None],
            "EPS Estimate": [Decimal("1.10"), Decimal("8.88"), None],
        },
        index=[
            datetime(2026, 1, 25, 9),
            datetime(2026, 1, 25, 16),
            datetime(2025, 10, 20),
        ],
    )

    results = earnings_events_from_frame(earnings_dates, source="fixture")

    # Source: DataFrame fixture immediately above; first duplicate row wins.
    assert results == [
        EarningsEventResult(
            event_date=date(2026, 1, 25),
            eps_actual=Decimal("1.20"),
            eps_estimate=Decimal("1.10"),
            source="fixture",
        ),
        EarningsEventResult(
            event_date=date(2025, 10, 20),
            eps_actual=None,
            eps_estimate=None,
            source="fixture",
        ),
    ]


def test_collect_job_uses_asset_universe_and_records_success(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    asset = Asset(symbol="AAPL", name="Apple", market="NASDAQ")
    watchlist = Watchlist(user_id=1, name="Main")
    db.add_all([asset, watchlist])
    db.commit()
    db.refresh(asset)
    db.refresh(watchlist)
    db.add(WatchlistItem(watchlist_id=watchlist.id, asset_id=asset.id))
    db.commit()
    monkeypatch.setattr(earnings, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        earnings,
        "get_earnings_provider",
        lambda: StaticEarningsProvider({"AAPL": [report()]}),
    )
    collect_earnings_job()
    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "earnings_collection"
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "targets": [{"symbol": "AAPL", "market": "NASDAQ"}]
    }
    assert db.scalars(select(EarningsReport)).one().symbol == "AAPL"
