from datetime import date, timedelta
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.domains.asset_events.schema import AssetEventRange, AssetEventType
from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsEvent
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset_and_events() -> int:
    today = date.today()
    with TestingSessionLocal() as db:
        asset = Asset(symbol="EVT", name="Events", market="NASDAQ")
        db.add(asset)
        db.flush()
        # Source: docs/designs/282-earnings-event-history.md service fixture.
        rows = [
            (today - timedelta(days=367), "1.00", "0.80"),
            (today - timedelta(days=366), "1.00", "0.80"),
            (today - timedelta(days=183), "0.80", "1.00"),
            (today - timedelta(days=92), "1.20", "1.00"),
            (today - timedelta(days=31), "1.00", None),
            (today, "1.00", "0"),
            (today + timedelta(days=1), "1.30", "1.00"),
        ]
        db.add_all(
            EarningsEvent(
                symbol=asset.symbol,
                market=asset.market,
                event_date=event_date,
                eps_actual=Decimal(actual) if actual is not None else None,
                eps_estimate=Decimal(estimate) if estimate is not None else None,
                source="fixture",
            )
            for event_date, actual, estimate in rows
        )
        db.commit()
        return asset.id


@pytest.mark.parametrize(
    ("range_", "expected_count"),
    [
        (AssetEventRange.ONE_MONTH, 2),
        (AssetEventRange.THREE_MONTHS, 3),
        (AssetEventRange.SIX_MONTHS, 4),
        (AssetEventRange.ONE_YEAR, 5),
    ],
)
def test_get_event_history_filters_range_boundaries_and_future_events(
    client: TestClient,
    range_: AssetEventRange,
    expected_count: int,
) -> None:
    set_current_user(1)
    asset_id = create_asset_and_events()

    response = client.get(
        f"/api/v1/assets/{asset_id}/events",
        params={"range": range_.value},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    assert data["range"] == range_.value
    assert len(data["events"]) == expected_count
    event_dates = [date.fromisoformat(item["event_date"]) for item in data["events"]]
    assert event_dates == sorted(event_dates)
    assert all(event_date <= date.today() for event_date in event_dates)
    assert all(item["event_type"] == AssetEventType.EARNINGS.value for item in data["events"])
    assert all("title" not in item for item in data["events"])


def test_get_event_history_derives_surprise_and_guards_missing_values(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset_and_events()

    data = cast(
        dict[str, Any],
        api_data(
            client.get(
                f"/api/v1/assets/{asset_id}/events",
                params={"range": "6M"},
            )
        ),
    )

    # Source: fixtures above: (actual - estimate) / abs(estimate) * 100.
    assert [item["eps_surprise_percent"] for item in data["events"]] == [
        "-20.00",
        "20.00",
        None,
        None,
    ]


def test_get_event_history_defaults_to_three_months_and_returns_empty_events(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as db:
        asset = Asset(symbol="EMPTYEVT", name="Empty Events", market="NASDAQ")
        db.add(asset)
        db.commit()
        db.refresh(asset)
        asset_id = asset.id

    response = client.get(f"/api/v1/assets/{asset_id}/events")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["range"] == "3M"
    assert data["events"] == []


def test_get_event_history_returns_404_for_missing_asset(client: TestClient) -> None:
    set_current_user(1)
    existing_asset_id = create_asset_and_events()

    response = client.get(f"/api/v1/assets/{existing_asset_id + 1}/events")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_event_history_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset_and_events()

    response = client.get(f"/api/v1/assets/{asset_id}/events")

    assert response.status_code == 401
