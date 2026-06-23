from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_meta, set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def create_watchlist(client: TestClient, name: str = "Core") -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": name})
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def add_item(
    client: TestClient, watchlist_id: int, asset_id: int, priority: int = 0
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/watchlists/{watchlist_id}/items",
        json={"asset_id": asset_id, "priority": priority},
    )
    assert response.status_code == 201
    body = response.json()
    return cast(dict[str, Any], body["data"])


def test_list_items_without_expand_excludes_asset_field(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/items")

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    assert "asset" not in data[0]


def test_list_items_with_expand_asset_includes_asset_object(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    item = data[0]
    assert "asset" in item
    brief = item["asset"]
    assert brief is not None
    assert brief["symbol"] == "AAPL"
    assert "name" in brief
    assert "price" in brief
    assert "change_percent" in brief
    assert "sector" in brief


def test_expand_asset_price_and_change_percent_are_strings(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    brief = data[0]["asset"]
    assert isinstance(brief["price"], str)
    assert isinstance(brief["change_percent"], str)
    # AAPL mock price is 195.64
    assert brief["price"] == "195.64"
    assert brief["change_percent"] == "1.26"


def test_expand_asset_mock_quote_for_tsla(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "TSLA")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    brief = data[0]["asset"]
    assert brief["symbol"] == "TSLA"
    assert brief["price"] == "182.31"
    assert brief["change_percent"] == "-1.45"


def test_expand_asset_with_multiple_items_returns_all(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    aapl = create_asset(client, "AAPL")
    tsla = create_asset(client, "TSLA")
    add_item(client, watchlist["id"], aapl["id"], priority=10)
    add_item(client, watchlist["id"], tsla["id"], priority=5)

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "asset"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 2
    symbols = {item["asset"]["symbol"] for item in data}
    assert symbols == {"AAPL", "TSLA"}
    assert api_meta(response) == {"page": 1, "size": 20, "total": 2}


def test_expand_asset_pagination_works(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    aapl = create_asset(client, "AAPL")
    tsla = create_asset(client, "TSLA")
    add_item(client, watchlist["id"], aapl["id"], priority=10)
    add_item(client, watchlist["id"], tsla["id"], priority=5)

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "asset", "size": 1, "page": 1},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert len(data) == 1
    assert api_meta(response) == {"page": 1, "size": 1, "total": 2}
    assert data[0]["asset"] is not None


def test_expand_other_value_excludes_asset(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client, "AAPL")
    add_item(client, watchlist["id"], asset["id"])

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        params={"expand": "other"},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert "asset" not in data[0]
