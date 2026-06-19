from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_error, api_meta, set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_watchlist(
    client: TestClient, name: str = "Core"
) -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": name})
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_create_watchlist_success(client: TestClient) -> None:
    set_current_user(1)

    data = create_watchlist(client)

    assert data["id"] == 1
    assert data["user_id"] == 1
    assert data["name"] == "Core"
    assert "created_at" in data


def test_list_watchlists_returns_only_current_users_lists(client: TestClient) -> None:
    set_current_user(1)
    owner_watchlist = create_watchlist(client, "Owner")
    set_current_user(2, "other@example.com")
    create_watchlist(client, "Other")
    set_current_user(1)

    response = client.get("/api/v1/watchlists")

    assert response.status_code == 200
    assert api_data(response) == [owner_watchlist]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_watchlists_uses_page_and_size(client: TestClient) -> None:
    set_current_user(1)
    create_watchlist(client, "First")
    second = create_watchlist(client, "Second")

    response = client.get("/api/v1/watchlists", params={"page": 2, "size": 1})

    assert response.status_code == 200
    assert api_data(response) == [second]
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_add_watchlist_item_success(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)

    response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={
            "asset_id": asset["id"],
            "priority": 10,
            "reason": "Core AI exposure",
            "tags": ["ai", "large-cap"],
            "memo": "Watch earnings.",
        },
    )

    assert response.status_code == 201
    data = cast(dict[str, Any], api_data(response))
    assert data["watchlist_id"] == watchlist["id"]
    assert data["asset_id"] == asset["id"]
    assert data["priority"] == 10
    assert data["reason"] == "Core AI exposure"
    assert data["tags"] == ["ai", "large-cap"]
    assert data["memo"] == "Watch earnings."
    assert "created_at" in data


def test_list_watchlist_items_round_trips_fields_and_paginates(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    first_asset = create_asset(client, "AAPL")
    second_asset = create_asset(client, "MSFT")
    client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={
            "asset_id": first_asset["id"],
            "priority": 20,
            "reason": "Long-term compounder",
            "tags": ["core"],
            "memo": "Review after earnings.",
        },
    )
    client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": second_asset["id"], "priority": 10},
    )

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"page": 2, "size": 1, "sort": "priority"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    assert data[0]["asset_id"] == first_asset["id"]
    assert data[0]["reason"] == "Long-term compounder"
    assert data[0]["tags"] == ["core"]
    assert data[0]["memo"] == "Review after earnings."
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_list_watchlist_items_supports_sort_values(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    first_asset = create_asset(client, "AAPL")
    second_asset = create_asset(client, "MSFT")
    client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": first_asset["id"], "priority": 1},
    )
    client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": second_asset["id"], "priority": 5},
    )

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"sort": "-priority"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["asset_id"] for item in data] == [
        second_asset["id"],
        first_asset["id"],
    ]


def test_list_watchlist_items_rejects_invalid_sort(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"sort": "asset_id"},
    )

    assert response.status_code == 422
    assert api_error(response)["code"] == "VALIDATION_ERROR"


def test_add_watchlist_item_rejects_duplicate_asset(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)
    payload = {"asset_id": asset["id"], "priority": 0}
    first_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json=payload,
    )
    assert first_response.status_code == 201

    response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json=payload,
    )

    assert response.status_code == 400
    assert api_error(response) == {
        "code": "WATCHLIST_ITEM_DUPLICATE",
        "message": "이미 관심 목록에 추가된 종목입니다.",
    }


def test_remove_watchlist_item_success(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)
    create_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": asset["id"], "priority": 0},
    )
    assert create_response.status_code == 201
    item = cast(dict[str, Any], api_data(create_response))

    response = client.delete(
        f"/api/v1/watchlists/{watchlist['id']}/items/{item['id']}",
    )

    assert response.status_code == 200
    assert api_data(response) is None


def test_watchlist_ownership_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)
    set_current_user(2, "other@example.com")

    response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": asset["id"], "priority": 0},
    )

    assert response.status_code == 403


def test_list_watchlist_items_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/items")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "WATCHLIST_FORBIDDEN",
        "message": "관심 목록 접근 권한이 없습니다.",
    }
