from datetime import datetime, timedelta, timezone
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.domains.alert_candidates.model import AlertCandidate
from app.domains.alert_candidates.types import (
    AlertCandidateStatus,
    AlertCandidateType,
    AlertImportance,
)
from app.domains.alerts.model import Alert
from app.domains.alerts.types import AlertStatus
from app.domains.assets.model import Asset
from app.domains.dashboard.schema import DashboardTrendSeriesResponse
from app.domains.dashboard.trend_service import DashboardTrendService
from app.domains.signals.model import Signal
from app.domains.signals.types import SignalType
from tests.conftest import api_data, api_error, set_current_user

FIXED_NOW = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def fixed_trend_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.domains.dashboard.trend_service.utc_now", lambda: FIXED_NOW)


def create_asset(db: Session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_alert(
    db: Session,
    *,
    user_id: int,
    signal_type: SignalType,
    created_at: datetime,
    symbol: str,
    status: AlertStatus = AlertStatus.UNREAD,
    expires_at: datetime | None = None,
) -> Alert:
    asset = create_asset(db, symbol)
    signal = Signal(
        asset_id=asset.id,
        signal_type=signal_type.value,
        score=80,
        risk_level="HIGH",
        reason="Trend test signal",
        expires_at=expires_at,
        created_at=created_at,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)

    alert = Alert(
        user_id=user_id,
        signal_id=signal.id,
        status=status.value,
        dedup_key=f"{user_id}:{symbol}:{signal_type.value}",
        created_at=created_at,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def create_candidate(
    db: Session,
    *,
    user_id: int,
    candidate_type: AlertCandidateType,
    importance: AlertImportance,
    created_at: datetime,
    status: AlertCandidateStatus = AlertCandidateStatus.UNREAD,
) -> AlertCandidate:
    candidate = AlertCandidate(
        user_id=user_id,
        candidate_type=candidate_type,
        importance=importance,
        status=status,
        title="Trend test candidate",
    )
    candidate.created_at = created_at
    db.add(candidate)
    db.commit()
    db.refresh(candidate)
    return candidate


def series_by_key(response: DashboardTrendSeriesResponse) -> dict[str, list[dict[str, Any]]]:
    return {
        series.key: [point.model_dump() for point in series.data]
        for series in response.series
    }


def test_dashboard_trends_returns_window_with_zero_fill_and_user_isolation(
    db: Session,
) -> None:
    event_date = FIXED_NOW - timedelta(days=2)
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.RISK_ALERT,
        created_at=event_date,
        symbol="RA1",
    )
    create_alert(
        db,
        user_id=2,
        signal_type=SignalType.RISK_ALERT,
        created_at=event_date,
        symbol="RA2",
    )

    response = DashboardTrendService(db).get_trends(user_id=1, days=5)

    by_key = series_by_key(response)
    assert response.days == 5
    assert list(by_key) == ["risk_alerts", "review_signals", "important_news"]
    assert all(len(points) == 5 for points in by_key.values())
    assert [point["date"] for point in by_key["risk_alerts"]] == [
        "2026-06-27",
        "2026-06-28",
        "2026-06-29",
        "2026-06-30",
        "2026-07-01",
    ]
    assert [point["count"] for point in by_key["risk_alerts"]] == [0, 0, 1, 0, 0]
    assert all(point["count"] == 0 for point in by_key["review_signals"])
    assert all(point["count"] == 0 for point in by_key["important_news"])


def test_dashboard_trends_maps_source_filters_to_expected_series(db: Session) -> None:
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.RISK_ALERT,
        created_at=FIXED_NOW,
        symbol="RA1",
    )
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.THESIS_BROKEN,
        created_at=FIXED_NOW,
        symbol="TB1",
    )
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.SELL_REVIEW,
        created_at=FIXED_NOW,
        symbol="SR1",
    )
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.OVERHEATED,
        created_at=FIXED_NOW,
        symbol="OH1",
    )
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.WATCH,
        created_at=FIXED_NOW,
        symbol="WC1",
    )
    create_candidate(
        db,
        user_id=1,
        candidate_type=AlertCandidateType.NEWS_SURGE,
        importance=AlertImportance.HIGH,
        created_at=FIXED_NOW,
    )
    create_candidate(
        db,
        user_id=1,
        candidate_type=AlertCandidateType.DISCLOSURE,
        importance=AlertImportance.HIGH,
        created_at=FIXED_NOW,
    )
    create_candidate(
        db,
        user_id=1,
        candidate_type=AlertCandidateType.PRICE_MOVEMENT,
        importance=AlertImportance.HIGH,
        created_at=FIXED_NOW,
    )
    create_candidate(
        db,
        user_id=1,
        candidate_type=AlertCandidateType.NEWS_SURGE,
        importance=AlertImportance.MEDIUM,
        created_at=FIXED_NOW,
    )

    by_key = series_by_key(DashboardTrendService(db).get_trends(user_id=1, days=1))

    assert by_key["risk_alerts"][0]["count"] == 2
    assert by_key["review_signals"][0]["count"] == 2
    assert by_key["important_news"][0]["count"] == 2


def test_dashboard_trends_counts_read_and_expired_events_by_created_at(
    db: Session,
) -> None:
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.RISK_ALERT,
        created_at=FIXED_NOW,
        symbol="RDR1",
        status=AlertStatus.READ,
    )
    create_alert(
        db,
        user_id=1,
        signal_type=SignalType.SELL_REVIEW,
        created_at=FIXED_NOW,
        symbol="EXP1",
        expires_at=FIXED_NOW - timedelta(days=1),
    )
    create_candidate(
        db,
        user_id=1,
        candidate_type=AlertCandidateType.NEWS_SURGE,
        importance=AlertImportance.HIGH,
        created_at=FIXED_NOW,
        status=AlertCandidateStatus.READ,
    )

    by_key = series_by_key(DashboardTrendService(db).get_trends(user_id=1, days=1))

    assert by_key["risk_alerts"][0]["count"] == 1
    assert by_key["review_signals"][0]["count"] == 1
    assert by_key["important_news"][0]["count"] == 1


def test_dashboard_trends_api_returns_enveloped_series(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/dashboard/trends", params={"days": 3})

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["days"] == 3
    assert [series["key"] for series in data["series"]] == [
        "risk_alerts",
        "review_signals",
        "important_news",
    ]
    assert all(len(series["data"]) == 3 for series in data["series"])
    assert all(
        set(point) == {"date", "count"}
        for series in data["series"]
        for point in series["data"]
    )


def test_dashboard_trends_api_requires_auth(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/trends")

    assert response.status_code == 401


def test_dashboard_trends_api_rejects_days_above_cap(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/dashboard/trends", params={"days": 91})

    assert response.status_code == 422
    error = api_error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "요청 값이 올바르지 않습니다."
