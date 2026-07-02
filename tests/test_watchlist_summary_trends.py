from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.signals.model import Signal
from app.domains.signals.types import SignalType
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.domains.watchlists.schema import WatchlistSummaryTrendResponse
from app.domains.watchlists.service import WatchlistService
from app.domains.watchlists.trend_service import WatchlistSummaryTrendService
from tests.conftest import api_data, api_error, set_current_user

FIXED_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_trend_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domains.watchlists.trend_service.utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr("app.domains.signals.repository.utc_now", lambda: FIXED_NOW)


def create_asset(db: Session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_watchlist(db: Session, *, user_id: int = 1, name: str = "Core") -> Watchlist:
    watchlist = Watchlist(user_id=user_id, name=name)
    db.add(watchlist)
    db.commit()
    db.refresh(watchlist)
    return watchlist


def create_item(
    db: Session,
    *,
    watchlist_id: int,
    asset_id: int,
    created_at: datetime,
) -> WatchlistItem:
    item = WatchlistItem(
        watchlist_id=watchlist_id,
        asset_id=asset_id,
        priority=0,
        created_at=created_at,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_signal(
    db: Session,
    *,
    asset_id: int,
    signal_type: SignalType = SignalType.RISK_ALERT,
    created_at: datetime,
    expires_at: datetime | None = None,
) -> Signal:
    signal = Signal(
        asset_id=asset_id,
        signal_type=signal_type.value,
        score=80,
        risk_level="HIGH",
        reason="Watchlist trend test signal.",
        created_at=created_at,
        expires_at=expires_at,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def series_by_key(
    response: WatchlistSummaryTrendResponse,
) -> dict[str, list[dict[str, Any]]]:
    return {
        series.key: [point.model_dump() for point in series.data]
        for series in response.series
    }


def create_api_watchlist(client: TestClient, name: str = "Core") -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": name})
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_watchlist_summary_trends_total_is_monotonic_zero_filled_and_matches_summary(
    db: Session,
) -> None:
    watchlist = create_watchlist(db)
    assets = [create_asset(db, symbol) for symbol in ["AAPL", "MSFT", "NVDA", "TSLA"]]
    created_ats = [
        FIXED_NOW - timedelta(days=20),
        datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 6, 30, 10, 0, tzinfo=timezone.utc),
        datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
    ]
    for asset, created_at in zip(assets, created_ats, strict=True):
        create_item(
            db,
            watchlist_id=watchlist.id,
            asset_id=asset.id,
            created_at=created_at,
        )

    response = WatchlistSummaryTrendService(db).get_trends(watchlist.id, user_id=1, days=5)

    by_key = series_by_key(response)
    totals = by_key["watchlist_total"]
    assert response.days == 5
    assert [point["date"] for point in totals] == [
        "2026-06-27",
        "2026-06-28",
        "2026-06-29",
        "2026-06-30",
        "2026-07-01",
    ]
    assert [point["count"] for point in totals] == [1, 1, 2, 3, 4]
    assert [point["count"] for point in totals] == sorted(point["count"] for point in totals)
    assert totals[-1]["count"] == WatchlistService(db).get_summary(watchlist.id, 1).total_count


def test_watchlist_summary_trends_empty_watchlist_returns_zero_series(db: Session) -> None:
    watchlist = create_watchlist(db)

    response = WatchlistSummaryTrendService(db).get_trends(watchlist.id, user_id=1, days=4)

    by_key = series_by_key(response)
    assert set(by_key) == {"watchlist_total", "risk_increasing"}
    assert all(len(points) == 4 for points in by_key.values())
    assert all(
        point["count"] == 0
        for points in by_key.values()
        for point in points
    )


def test_watchlist_summary_trends_risk_increasing_as_of_unique_and_matches_summary(
    db: Session,
) -> None:
    watchlist = create_watchlist(db)
    assets = [create_asset(db, symbol) for symbol in ["AAPL", "MSFT", "NVDA", "GOOGL"]]
    for asset in assets:
        create_item(
            db,
            watchlist_id=watchlist.id,
            asset_id=asset.id,
            created_at=FIXED_NOW - timedelta(days=10),
        )
    create_signal(
        db,
        asset_id=assets[0].id,
        created_at=datetime(2026, 6, 28, 10, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc),
    )
    create_signal(
        db,
        asset_id=assets[1].id,
        created_at=datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
    )
    create_signal(
        db,
        asset_id=assets[1].id,
        created_at=datetime(2026, 6, 29, 11, 0, tzinfo=timezone.utc),
    )
    create_signal(
        db,
        asset_id=assets[2].id,
        created_at=datetime(2026, 7, 1, 8, 0, tzinfo=timezone.utc),
        expires_at=datetime(2026, 7, 2, 8, 0, tzinfo=timezone.utc),
    )
    create_signal(
        db,
        asset_id=assets[3].id,
        signal_type=SignalType.WATCH,
        created_at=datetime(2026, 6, 29, 10, 0, tzinfo=timezone.utc),
    )

    response = WatchlistSummaryTrendService(db).get_trends(watchlist.id, user_id=1, days=5)

    risk = series_by_key(response)["risk_increasing"]
    assert [point["count"] for point in risk] == [0, 1, 2, 1, 2]
    assert (
        risk[-1]["count"]
        == WatchlistService(db).get_summary(watchlist.id, 1).risk_increasing_count
    )


def test_watchlist_summary_trends_api_contract_and_days_boundaries(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_api_watchlist(client)

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/summary/trends",
        params={"days": 1},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["days"] == 1
    assert {series["key"] for series in data["series"]} == {
        "watchlist_total",
        "risk_increasing",
    }
    assert all(len(series["data"]) == 1 for series in data["series"])
    assert all(
        set(point) == {"date", "count"}
        for series in data["series"]
        for point in series["data"]
    )

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/summary/trends",
        params={"days": 90},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["days"] == 90
    assert all(len(series["data"]) == 90 for series in data["series"])


@pytest.mark.parametrize("days", [0, 91])
def test_watchlist_summary_trends_api_rejects_days_out_of_range(
    client: TestClient,
    days: int,
) -> None:
    set_current_user(1)
    watchlist = create_api_watchlist(client)

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/summary/trends",
        params={"days": days},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_watchlist_summary_trends_api_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/watchlists/1/summary/trends")

    assert response.status_code == 401


def test_watchlist_summary_trends_api_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_api_watchlist(client)
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/summary/trends")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "WATCHLIST_FORBIDDEN",
        "message": "관심 목록 접근 권한이 없습니다.",
    }


def test_watchlist_summary_trends_api_returns_404_for_missing_watchlist(
    client: TestClient,
) -> None:
    set_current_user(1)

    response = client.get("/api/v1/watchlists/999/summary/trends")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "WATCHLIST_NOT_FOUND",
        "message": "관심 목록을 찾을 수 없습니다.",
    }
