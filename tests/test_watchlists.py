from datetime import datetime, timedelta, timezone
from typing import Any, cast

from fastapi.testclient import TestClient

from app.domains.signals.types import SignalType
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


def create_signal(
    client: TestClient,
    asset_id: int,
    signal_type: SignalType = SignalType.RISK_ALERT,
    expires_at: datetime | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/signals",
        json={
            "asset_id": asset_id,
            "signal_type": signal_type.value,
            "score": 80,
            "risk_level": "HIGH",
            "reason": "Watchlist summary test signal.",
            "expires_at": expires_at.isoformat() if expires_at is not None else None,
        },
    )
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


def test_get_watchlist_summary_counts_total_and_active_risk_assets(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    risk_asset = create_asset(client, "AAPL")
    expired_asset = create_asset(client, "MSFT")
    other_type_asset = create_asset(client, "GOOGL")
    quiet_asset = create_asset(client, "NVDA")
    for asset in [risk_asset, expired_asset, other_type_asset, quiet_asset]:
        response = client.post(
            f"/api/v1/watchlists/{watchlist['id']}/items",
            json={"asset_id": asset["id"], "priority": 0},
        )
        assert response.status_code == 201
    create_signal(client, risk_asset["id"])
    create_signal(client, risk_asset["id"])
    create_signal(
        client,
        expired_asset["id"],
        expires_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    create_signal(client, other_type_asset["id"], SignalType.WATCH)

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["total_count"] == 4
    assert data["risk_increasing_count"] == 1
    assert len(data["recent_items"]) == 4


def test_get_watchlist_summary_returns_recent_items_sorted_and_limited(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "TSLA", "AMZN"]
    assets = [create_asset(client, symbol) for symbol in symbols]
    for asset in assets:
        response = client.post(
            f"/api/v1/watchlists/{watchlist['id']}/items",
            json={"asset_id": asset["id"], "priority": 0},
        )
        assert response.status_code == 201

    response = client.get(
        f"/api/v1/watchlists/{watchlist['id']}/summary",
        params={"recent_limit": 3},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    recent_items = cast(list[dict[str, Any]], data["recent_items"])
    assert [item["symbol"] for item in recent_items] == ["AMZN", "TSLA", "NVDA"]
    assert [item["name"] for item in recent_items] == [
        "AMZN Inc.",
        "TSLA Inc.",
        "NVDA Inc.",
    ]
    assert all("created_at" in item for item in recent_items)


def test_get_watchlist_summary_returns_empty_values_for_empty_watchlist(
    client: TestClient,
) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/summary")

    assert response.status_code == 200
    assert api_data(response) == {
        "total_count": 0,
        "risk_increasing_count": 0,
        "recent_items": [],
    }


def test_get_watchlist_summary_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    set_current_user(2, "other@example.com")

    response = client.get(f"/api/v1/watchlists/{watchlist['id']}/summary")

    assert response.status_code == 403
    assert api_error(response) == {
        "code": "WATCHLIST_FORBIDDEN",
        "message": "관심 목록 접근 권한이 없습니다.",
    }


def test_get_watchlist_summary_returns_404_for_missing_watchlist(
    client: TestClient,
) -> None:
    set_current_user(1)

    response = client.get("/api/v1/watchlists/999/summary")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "WATCHLIST_NOT_FOUND",
        "message": "관심 목록을 찾을 수 없습니다.",
    }


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
