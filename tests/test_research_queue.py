from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsEvent, EarningsReport
from app.domains.news.model import NewsItem
from app.domains.prices.model import StockPriceBar
from app.domains.reports.model import ResearchReport
from app.domains.research_queue.schema import ResearchStatus
from app.domains.research_queue.service import ResearchQueueService
from app.domains.signals.model import Signal
from app.domains.valuation.model import ValuationSnapshot
from tests.conftest import api_data, api_meta, set_current_user

FIXED_NOW = datetime(2026, 7, 13, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def fixed_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domains.research_queue.service.utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("app.domains.research_queue.repository.utc_now", lambda: FIXED_NOW)


def _asset(db: Session, symbol: str, *, active: bool = True) -> Asset:
    asset = Asset(
        symbol=symbol,
        name=f"{symbol} Inc.",
        market="NASDAQ",
        is_active=active,
    )
    db.add(asset)
    db.flush()
    return asset


def _news(db: Session, asset: Asset, created_at: datetime = FIXED_NOW) -> None:
    db.add(
        NewsItem(
            asset_id=asset.id,
            title=f"{asset.symbol} news",
            url=f"https://example.com/{asset.symbol}",
            source="fixture",
            created_at=created_at,
        )
    )


def _price(db: Session, asset: Asset) -> None:
    db.add(
        StockPriceBar(
            symbol=asset.symbol,
            market=asset.market,
            interval="1d",
            timestamp=FIXED_NOW,
            open_price=Decimal("100"),
            high_price=Decimal("101"),
            low_price=Decimal("99"),
            close_price=Decimal("100"),
            adjusted_close_price=Decimal("100"),
            volume=100,
            currency="USD",
            source="fixture",
        )
    )


def _earnings(db: Session, asset: Asset) -> None:
    db.add(
        EarningsReport(
            symbol=asset.symbol,
            market=asset.market,
            period="2026Q2",
            period_end=date(2026, 6, 30),
            source="fixture",
        )
    )


def _valuation(db: Session, asset: Asset) -> None:
    db.add(
        ValuationSnapshot(
            symbol=asset.symbol,
            market=asset.market,
            as_of=date(2026, 7, 13),
            source="fixture",
        )
    )


def _report(
    db: Session,
    asset: Asset,
    *,
    created_at: datetime,
    factors: str = '["Margin pressure. Monitor costs."]',
) -> None:
    db.add(
        ResearchReport(
            asset_id=asset.id,
            summary="Fixture report",
            negative_factors=factors,
            created_at=created_at,
        )
    )


def _signal(
    db: Session,
    asset: Asset,
    signal_type: str = "RISK_ALERT",
    *,
    reason: str = "Risk increased. Review evidence.",
    created_at: datetime = FIXED_NOW,
) -> None:
    db.add(
        Signal(
            asset_id=asset.id,
            signal_type=signal_type,
            score=90,
            reason=reason,
            expires_at=FIXED_NOW + timedelta(days=1),
            created_at=created_at,
        )
    )


def _add_axes(db: Session, asset: Asset, count: int, *, news_at: datetime = FIXED_NOW) -> None:
    if count >= 1:
        _news(db, asset, news_at)
    if count >= 2:
        _price(db, asset)
    if count >= 3:
        _earnings(db, asset)
    if count >= 4:
        _valuation(db, asset)


def test_status_rules_and_completeness_use_batched_data_fixtures(db: Session) -> None:
    analyzed = _asset(db, "ANALYZED")
    attention = _asset(db, "ATTENTION")
    collecting = _asset(db, "COLLECTING")
    insufficient = _asset(db, "INSUFFICIENT")
    stale = _asset(db, "STALE")
    completeness_assets = [_asset(db, f"AXIS{count}") for count in range(5)]

    _add_axes(db, analyzed, 3)
    _add_axes(db, attention, 4)
    _signal(db, attention)
    _add_axes(db, collecting, 2)
    _add_axes(db, insufficient, 1)
    _add_axes(db, stale, 3, news_at=FIXED_NOW - timedelta(days=31))
    for count, asset in enumerate(completeness_assets):
        _add_axes(db, asset, count)
    db.commit()

    items, _, total = ResearchQueueService(db).list_queue(None, 0, 20)
    by_symbol = {item.symbol: item for item in items}

    assert total == 10
    assert by_symbol["ANALYZED"].research_status == ResearchStatus.ANALYZED
    assert by_symbol["ATTENTION"].research_status == ResearchStatus.NEEDS_ATTENTION
    assert by_symbol["COLLECTING"].research_status == ResearchStatus.COLLECTING
    assert by_symbol["INSUFFICIENT"].research_status == ResearchStatus.INSUFFICIENT
    assert by_symbol["STALE"].research_status == ResearchStatus.STALE
    assert [by_symbol[f"AXIS{count}"].completeness_pct for count in range(5)] == [
        0,
        25,
        50,
        75,
        100,
    ]
    assert by_symbol["ATTENTION"].key_issue == "Risk increased."
    assert by_symbol["ATTENTION"].signal_type == "RISK_ALERT"
    assert by_symbol["ANALYZED"].stance is None
    assert by_symbol["ANALYZED"].headline is None


def test_pending_analysis_preserves_completeness_priority_and_needs_filter(
    db: Session,
) -> None:
    pending = _asset(db, "PENDING")
    collecting = _asset(db, "PENDING_LOW")
    for asset in (pending, collecting):
        _price(db, asset)
        _earnings(db, asset)
    _valuation(db, pending)
    db.commit()

    items, _, total = ResearchQueueService(db).list_queue("needs_research", 0, 20)
    by_symbol = {item.symbol: item for item in items}

    assert total == 2
    assert by_symbol["PENDING"].research_status == ResearchStatus.PENDING_ANALYSIS
    assert by_symbol["PENDING_LOW"].research_status == ResearchStatus.COLLECTING


def test_unknown_signal_type_is_not_exposed(db: Session) -> None:
    asset = _asset(db, "UNKNOWN_SIGNAL")
    _add_axes(db, asset, 4)
    _signal(db, asset, "FUTURE_SIGNAL")
    db.commit()

    items, _, _ = ResearchQueueService(db).list_queue(None, 0, 20)

    assert items[0].signal_type is None


def test_list_queue_calculates_reference_time_once(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    asset = _asset(db, "SINGLE_NOW")
    _add_axes(db, asset, 4)
    db.commit()
    call_count = 0

    def counting_now() -> datetime:
        nonlocal call_count
        call_count += 1
        return FIXED_NOW

    monkeypatch.setattr("app.domains.research_queue.service.utc_now", counting_now)

    ResearchQueueService(db).list_queue("recently_updated", 0, 20)

    assert call_count == 1


def test_key_issue_falls_back_to_latest_report_first_factor(db: Session) -> None:
    asset = _asset(db, "REPORT")
    _report(db, asset, created_at=FIXED_NOW)
    db.commit()

    items, _, _ = ResearchQueueService(db).list_queue(None, 0, 20)

    assert items[0].key_issue == "Margin pressure."
    assert items[0].last_updated_at == FIXED_NOW.replace(tzinfo=None)


def test_all_filters_include_and_exclude_boundaries(db: Session) -> None:
    today_start = datetime(2026, 7, 13, tzinfo=UTC)
    risk = _asset(db, "RISK")
    collecting = _asset(db, "COLLECT")
    analyzed = _asset(db, "DONE")
    upcoming_today = _asset(db, "TODAY")
    upcoming_day_30 = _asset(db, "DAY30")
    outside_day_31 = _asset(db, "DAY31")
    before_today = _asset(db, "BEFORE_TODAY")

    _add_axes(db, risk, 4)
    _signal(db, risk, "THESIS_BROKEN")
    _add_axes(db, collecting, 2)
    _add_axes(db, analyzed, 4, news_at=today_start)
    _add_axes(db, upcoming_today, 4)
    _add_axes(db, upcoming_day_30, 4)
    _add_axes(db, outside_day_31, 4)
    _add_axes(db, before_today, 4, news_at=today_start - timedelta(microseconds=1))
    for asset, event_date in (
        (upcoming_today, FIXED_NOW.date()),
        (upcoming_day_30, FIXED_NOW.date() + timedelta(days=30)),
        (outside_day_31, FIXED_NOW.date() + timedelta(days=31)),
    ):
        db.add(
            EarningsEvent(
                symbol=asset.symbol,
                market=asset.market,
                event_date=event_date,
                source="fixture",
            )
        )
    db.commit()
    service = ResearchQueueService(db)

    needs, _, _ = service.list_queue("needs_research", 0, 20)
    risks, _, _ = service.list_queue("risk_increasing", 0, 20)
    upcoming, _, _ = service.list_queue("earnings_upcoming", 0, 20)
    recent, _, _ = service.list_queue("recently_updated", 0, 20)

    assert {item.symbol for item in needs} == {"RISK", "COLLECT"}
    assert {item.symbol for item in risks} == {"RISK"}
    assert {item.symbol for item in upcoming} == {"TODAY", "DAY30"}
    assert "BEFORE_TODAY" not in {item.symbol for item in recent}
    assert "DONE" in {item.symbol for item in recent}


def test_summary_is_unfiltered_and_api_meta_is_filtered_and_paginated(
    client: TestClient,
) -> None:
    set_current_user(1)
    from tests.conftest import TestingSessionLocal

    with TestingSessionLocal() as db:
        risk = _asset(db, "RISK")
        collecting = _asset(db, "COLLECT")
        analyzed = _asset(db, "DONE")
        _add_axes(db, risk, 4)
        _signal(db, risk)
        _add_axes(db, collecting, 2)
        _add_axes(db, analyzed, 4)
        db.commit()

    response = client.get(
        "/api/v1/research-queue",
        params={"filter": "needs_research", "page": 2, "size": 1},
    )

    assert response.status_code == 200
    data = api_data(response)
    assert len(data["items"]) == 1
    assert data["summary"] == {
        "total_research_count": 3,
        "needs_attention_count": 1,
        "updated_today_count": 3,
        "insufficient_count": 0,
    }
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_unknown_filter_is_rejected(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/research-queue", params={"filter": "unknown"})

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_query_count_does_not_grow_with_asset_count(db: Session) -> None:
    for index in range(5):
        asset = _asset(db, f"BATCH{index}")
        _add_axes(db, asset, 4)
    db.commit()
    statement_count = 0

    def count_selects(
        conn: object,
        cursor: object,
        statement: str,
        parameters: object,
        context: object,
        executemany: bool,
    ) -> None:
        nonlocal statement_count
        if statement.lstrip().upper().startswith("SELECT"):
            statement_count += 1

    engine = db.get_bind()
    assert isinstance(engine, Engine)
    event.listen(engine, "before_cursor_execute", count_selects)
    try:
        ResearchQueueService(db).list_queue(None, 0, 20)
    finally:
        event.remove(engine, "before_cursor_execute", count_selects)

    assert statement_count == 11
