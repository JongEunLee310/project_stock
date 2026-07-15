from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from tests.conftest import TestingSessionLocal, api_data, api_error, set_current_user


def create_asset(symbol: str = "AAPL", market: str = "NASDAQ") -> int:
    with TestingSessionLocal() as db:
        asset = Asset(symbol=symbol, name=symbol, market=market)
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset.id


def test_get_analyst_opinions_returns_recent_mock_items(client: TestClient) -> None:
    set_current_user(1)
    asset_id = create_asset()

    response = client.get(
        f"/api/v1/assets/{asset_id}/analyst-opinions", params={"limit": 2}
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["asset_id"] == asset_id
    assert len(data["opinions"]) == 2
    assert data["opinions"][0] == {
        "firm": "JPMorgan",
        "action": "main",
        "to_grade": "Overweight",
        "from_grade": "Neutral",
        "price_target": "250.00",
        "prior_price_target": "240.00",
        "price_target_action": "Raises",
        "published_at": "2026-07-15T00:00:00Z",
    }


def test_get_analyst_opinions_returns_empty_for_unsupported_asset(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_id = create_asset("005930", "KOSPI")

    response = client.get(f"/api/v1/assets/{asset_id}/analyst-opinions")

    assert response.status_code == 200
    assert api_data(response) == {"asset_id": asset_id, "opinions": []}


def test_get_analyst_opinions_validates_limit(client: TestClient) -> None:
    set_current_user(1)
    asset_id = create_asset()

    assert client.get(
        f"/api/v1/assets/{asset_id}/analyst-opinions", params={"limit": 0}
    ).status_code == 422
    assert client.get(
        f"/api/v1/assets/{asset_id}/analyst-opinions", params={"limit": 51}
    ).status_code == 422


def test_get_analyst_opinions_returns_404_for_missing_asset(
    client: TestClient,
) -> None:
    set_current_user(1)

    response = client.get("/api/v1/assets/999/analyst-opinions")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_analyst_opinions_requires_authentication(client: TestClient) -> None:
    asset_id = create_asset()

    response = client.get(f"/api/v1/assets/{asset_id}/analyst-opinions")

    assert response.status_code == 401
