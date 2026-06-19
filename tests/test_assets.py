from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from tests.conftest import TestingSessionLocal, api_data, api_error, api_meta


def asset_payload(symbol: str = "AAPL", market: str = "NASDAQ") -> dict[str, str]:
    return {
        "symbol": symbol,
        "name": "Apple Inc.",
        "market": market,
    }


def create_asset(client: TestClient, payload: dict[str, str] | None = None) -> dict[str, Any]:
    response = client.post("/api/v1/assets", json=payload or asset_payload())
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_register_asset_success(client: TestClient) -> None:
    data = create_asset(client)

    assert data["id"] == 1
    assert data["symbol"] == "AAPL"
    assert data["name"] == "Apple Inc."
    assert data["market"] == "NASDAQ"
    assert data["is_active"] is True
    assert "created_at" in data


def test_register_asset_rejects_duplicate_symbol_market(client: TestClient) -> None:
    create_asset(client)

    response = client.post("/api/v1/assets", json=asset_payload())

    assert response.status_code == 400
    assert api_error(response) == {
        "code": "ASSET_DUPLICATE",
        "message": "이미 등록된 종목입니다.",
    }


def test_list_assets(client: TestClient) -> None:
    first_asset = create_asset(client)
    second_asset = create_asset(
        client,
        {
            "symbol": "MSFT",
            "name": "Microsoft Corporation",
            "market": "NASDAQ",
        },
    )

    response = client.get("/api/v1/assets")

    assert response.status_code == 200
    assert api_data(response) == [first_asset, second_asset]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 2}


def test_list_assets_filters_by_is_active(client: TestClient) -> None:
    active_asset = create_asset(client)
    with TestingSessionLocal() as db:
        db.add(
            Asset(
                symbol="DELISTED",
                name="Inactive Asset",
                market="NASDAQ",
                is_active=False,
            )
        )
        db.commit()

    response = client.get("/api/v1/assets", params={"is_active": True})

    assert response.status_code == 200
    assert api_data(response) == [active_asset]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_assets_uses_page_and_size(client: TestClient) -> None:
    create_asset(client)
    second_asset = create_asset(
        client,
        {
            "symbol": "MSFT",
            "name": "Microsoft Corporation",
            "market": "NASDAQ",
        },
    )

    response = client.get("/api/v1/assets", params={"page": 2, "size": 1})

    assert response.status_code == 200
    assert api_data(response) == [second_asset]
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_get_asset_detail(client: TestClient) -> None:
    asset = create_asset(client)

    response = client.get(f"/api/v1/assets/{asset['id']}")

    assert response.status_code == 200
    assert api_data(response) == asset


def test_get_asset_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/assets/999")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }
