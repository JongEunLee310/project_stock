from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.assets.model import Asset
from tests.conftest import (
    TestingSessionLocal,
    api_data,
    api_error,
    api_meta,
    set_current_user,
)


def asset_payload(symbol: str = "AAPL", market: str = "NASDAQ") -> dict[str, str]:
    return {
        "symbol": symbol,
        "name": "Apple Inc.",
        "market": market,
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "description": "Makes devices and services.",
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


def test_get_asset_detail_with_mock_quote(client: TestClient) -> None:
    asset = create_asset(client)

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["id"] == asset["id"]
    assert data["symbol"] == "AAPL"
    assert data["market"] == "NASDAQ"
    assert data["price"] == "195.64"
    assert data["previous_close"] == "193.20"
    assert data["change"] == "2.44"
    assert data["change_percent"] == "1.26"
    assert data["currency"] == "USD"
    assert data["sector"] == "Technology"
    assert data["industry"] == "Consumer Electronics"
    assert data["description"] == "Makes devices and services."
    assert data["as_of"] == "2026-06-19T00:00:00Z"


def test_get_asset_detail_uses_mock_fallback_for_unknown_symbol(
    client: TestClient,
) -> None:
    asset = create_asset(
        client,
        {
            "symbol": "ZZZZ",
            "name": "Unknown Mock",
            "market": "NASDAQ",
        },
    )

    response = client.get(f"/api/v1/assets/{asset['id']}/detail")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["symbol"] == "ZZZZ"
    assert data["price"] == "210"
    assert data["change"] == "1.00"


def test_get_asset_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/assets/999")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_asset_detail_returns_404_when_missing(client: TestClient) -> None:
    response = client.get("/api/v1/assets/999/detail")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_get_research_summary_returns_deterministic_mock_data(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset = create_asset(client)

    first_response = client.get(f"/api/v1/assets/{asset['id']}/research-summary")
    second_response = client.get(f"/api/v1/assets/{asset['id']}/research-summary")

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    first_data = cast(dict[str, Any], api_data(first_response))
    assert first_data == api_data(second_response)
    assert first_data["asset_id"] == asset["id"]
    assert first_data["positive_factors"]
    assert first_data["negative_factors"]
    assert first_data["items_to_verify"]
    assert first_data["sources"]
    assert first_data["updated_at"] == "2026-06-19T00:00:00Z"


def test_get_research_summary_returns_404_when_missing(client: TestClient) -> None:
    set_current_user(1)

    response = client.get("/api/v1/assets/999/research-summary")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }
