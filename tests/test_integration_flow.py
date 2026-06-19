from typing import Any, cast

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def stable_password_hashing(monkeypatch: pytest.MonkeyPatch) -> None:
    def hash_password(password: str) -> str:
        return f"hashed:{password}"

    def verify_password(plain_password: str, hashed_password: str) -> bool:
        return hashed_password == hash_password(plain_password)

    monkeypatch.setattr("app.domains.users.service.hash_password", hash_password)
    monkeypatch.setattr("app.domains.users.service.verify_password", verify_password)


def register_and_login(client: TestClient) -> dict[str, str]:
    register_response = client.post(
        "/api/v1/auth/register",
        json={"email": "flow@example.com", "password": "correct-password"},
    )
    assert register_response.status_code == 201

    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": "flow@example.com", "password": "correct-password"},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_asset(client: TestClient, symbol: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_authenticated_http_flow_creates_risk_alert_signal(
    client: TestClient,
) -> None:
    headers = register_and_login(client)
    apple = create_asset(client, "AAPL")
    microsoft = create_asset(client, "MSFT")

    watchlist_response = client.post(
        "/api/v1/watchlists",
        headers=headers,
        json={"name": "Core"},
    )
    assert watchlist_response.status_code == 201
    watchlist = watchlist_response.json()

    item_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        headers=headers,
        json={"asset_id": apple["id"], "priority": 10},
    )
    assert item_response.status_code == 201
    assert item_response.json()["watchlist_id"] == watchlist["id"]
    assert item_response.json()["asset_id"] == apple["id"]

    thesis_response = client.post(
        "/api/v1/theses",
        headers=headers,
        json={
            "asset_id": apple["id"],
            "summary": "Services growth offsets hardware cyclicality.",
            "risk_factors": "Margin compression",
            "invalidation_conditions": "Revenue growth below 5%",
        },
    )
    assert thesis_response.status_code == 201
    thesis = thesis_response.json()
    assert thesis["asset_id"] == apple["id"]

    portfolio_response = client.post(
        "/api/v1/portfolios",
        headers=headers,
        json={"name": "Long Term", "concentration_threshold": "0.6"},
    )
    assert portfolio_response.status_code == 201
    portfolio = portfolio_response.json()

    apple_position_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        headers=headers,
        json={"asset_id": apple["id"], "quantity": "3", "avg_buy_price": "100"},
    )
    assert apple_position_response.status_code == 201
    assert apple_position_response.json()["asset_id"] == apple["id"]

    microsoft_position_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        headers=headers,
        json={"asset_id": microsoft["id"], "quantity": "1", "avg_buy_price": "100"},
    )
    assert microsoft_position_response.status_code == 201
    assert microsoft_position_response.json()["asset_id"] == microsoft["id"]

    check_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/check",
        headers=headers,
    )
    assert check_response.status_code == 200
    check_data = check_response.json()
    assert check_data["summary"]["portfolio_id"] == portfolio["id"]
    assert len(check_data["created_signals"]) == 1

    created_signal = check_data["created_signals"][0]
    assert created_signal["asset_id"] == apple["id"]
    assert created_signal["signal_type"] == "RISK_ALERT"
    assert created_signal["evidence"]["portfolio_id"] == portfolio["id"]

    signals_response = client.get(
        "/api/v1/signals",
        headers=headers,
        params={"asset_id": apple["id"]},
    )
    assert signals_response.status_code == 200
    signals = signals_response.json()
    assert [signal["id"] for signal in signals] == [created_signal["id"]]
