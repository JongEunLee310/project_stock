from datetime import datetime, timezone
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from app.domains.catalysts.schema import CatalystEventType
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(symbol: str = "AAPL") -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def test_get_catalysts_returns_sorted_future_events_with_valid_types(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()
    today = datetime.now(timezone.utc).date()

    response = client.get(f"/api/v1/assets/{asset_id}/catalysts")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    events = data["events"]
    assert 4 <= len(events) <= 5
    event_dates = [datetime.fromisoformat(event["event_date"]).date() for event in events]
    assert event_dates == sorted(event_dates)
    assert all(event_date > today for event_date in event_dates)
    assert all(event["title"] for event in events)
    assert all(
        event["event_type"] in {event_type.value for event_type in CatalystEventType}
        for event in events
    )
    assert all(isinstance(event["is_estimated"], bool) for event in events)


def test_get_catalysts_applies_limit_and_is_deterministic(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset()

    first_response = client.get(
        f"/api/v1/assets/{asset_id}/catalysts",
        params={"limit": 2},
    )
    second_response = client.get(
        f"/api/v1/assets/{asset_id}/catalysts",
        params={"limit": 2},
    )

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_data = cast(dict[str, Any], api_data(first_response))
    second_data = cast(dict[str, Any], api_data(second_response))
    assert len(first_data["events"]) == 2
    assert first_data == second_data


def test_get_catalysts_returns_404_for_missing_asset(client: TestClient) -> None:
    set_current_user(1)
    existing_asset_id = create_asset()
    missing_asset_id = existing_asset_id + 1

    response = client.get(f"/api/v1/assets/{missing_asset_id}/catalysts")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_catalysts_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/catalysts")

    assert response.status_code == 401
