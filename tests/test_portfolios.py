from decimal import Decimal
from typing import Any, cast

from fastapi.testclient import TestClient

from tests.conftest import api_data, api_meta, set_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def create_portfolio(
    client: TestClient,
    name: str = "Long Term",
    concentration_threshold: str | None = None,
) -> dict[str, Any]:
    payload = {"name": name}
    if concentration_threshold is not None:
        payload["concentration_threshold"] = concentration_threshold
    response = client.post("/api/v1/portfolios", json=payload)
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def add_position(
    client: TestClient,
    portfolio_id: int,
    asset_id: int,
    quantity: str = "10.5",
    avg_buy_price: str = "123.45",
) -> dict[str, Any]:
    response = client.post(
        f"/api/v1/portfolios/{portfolio_id}/positions",
        json={
            "asset_id": asset_id,
            "quantity": quantity,
            "avg_buy_price": avg_buy_price,
        },
    )
    assert response.status_code == 201
    return cast(dict[str, Any], api_data(response))


def test_create_portfolio_success(client: TestClient) -> None:
    set_current_user(1)

    data = create_portfolio(client)

    assert data["id"] == 1
    assert data["user_id"] == 1
    assert data["name"] == "Long Term"
    assert Decimal(data["concentration_threshold"]) == Decimal("0.4")
    assert "created_at" in data


def test_create_portfolio_accepts_concentration_threshold(client: TestClient) -> None:
    set_current_user(1)

    data = create_portfolio(client, concentration_threshold="0.35")

    assert Decimal(data["concentration_threshold"]) == Decimal("0.35")


def test_list_portfolios_returns_only_current_users_portfolios(
    client: TestClient,
) -> None:
    set_current_user(1)
    owner_portfolio = create_portfolio(client, "Owner")
    set_current_user(2, "other@example.com")
    create_portfolio(client, "Other")
    set_current_user(1)

    response = client.get("/api/v1/portfolios")

    assert response.status_code == 200
    assert api_data(response) == [owner_portfolio]
    assert api_meta(response) == {"page": 1, "size": 20, "total": 1}


def test_list_portfolios_uses_page_and_size(client: TestClient) -> None:
    set_current_user(1)
    create_portfolio(client, "First")
    second = create_portfolio(client, "Second")

    response = client.get("/api/v1/portfolios", params={"page": 2, "size": 1})

    assert response.status_code == 200
    assert api_data(response) == [second]
    assert api_meta(response) == {"page": 2, "size": 1, "total": 2}


def test_add_position_success(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)

    response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json={
            "asset_id": asset["id"],
            "quantity": "10.5",
            "avg_buy_price": "123.45",
        },
    )

    assert response.status_code == 201
    data = cast(dict[str, Any], api_data(response))
    assert data["portfolio_id"] == portfolio["id"]
    assert data["asset_id"] == asset["id"]
    assert Decimal(data["quantity"]) == Decimal("10.5")
    assert Decimal(data["avg_buy_price"]) == Decimal("123.45")
    assert "created_at" in data


def test_add_position_returns_404_for_missing_portfolio(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    response = client.post(
        "/api/v1/portfolios/999/positions",
        json={
            "asset_id": asset["id"],
            "quantity": "1",
            "avg_buy_price": "100",
        },
    )

    assert response.status_code == 404


def test_add_position_returns_404_for_missing_asset(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)

    response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json={
            "asset_id": 999,
            "quantity": "1",
            "avg_buy_price": "100",
        },
    )

    assert response.status_code == 404


def test_update_position_quantity_and_average_price(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    position = add_position(client, portfolio["id"], asset["id"])

    quantity_response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}/positions/{position['id']}",
        json={"quantity": "15.25"},
    )
    assert quantity_response.status_code == 200
    quantity_data = cast(dict[str, Any], api_data(quantity_response))
    assert Decimal(quantity_data["quantity"]) == Decimal("15.25")
    assert Decimal(quantity_data["avg_buy_price"]) == Decimal("123.45")

    price_response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}/positions/{position['id']}",
        json={"avg_buy_price": "140.125"},
    )
    assert price_response.status_code == 200
    price_data = cast(dict[str, Any], api_data(price_response))
    assert Decimal(price_data["quantity"]) == Decimal("15.25")
    assert Decimal(price_data["avg_buy_price"]) == Decimal("140.125")


def test_update_position_returns_404_for_missing_position(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)

    response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}/positions/999",
        json={"quantity": "1"},
    )

    assert response.status_code == 404


def test_update_position_rejects_empty_body(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    position = add_position(client, portfolio["id"], asset["id"])

    response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}/positions/{position['id']}",
        json={},
    )

    assert response.status_code == 422


def test_delete_position_success(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    position = add_position(client, portfolio["id"], asset["id"])

    response = client.delete(
        f"/api/v1/portfolios/{portfolio['id']}/positions/{position['id']}",
    )

    assert response.status_code == 200
    assert api_data(response) is None


def test_portfolio_ownership_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    set_current_user(2, "other@example.com")

    response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json={
            "asset_id": asset["id"],
            "quantity": "1",
            "avg_buy_price": "100",
        },
    )

    assert response.status_code == 403


def test_add_position_rejects_duplicate_asset(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    asset = create_asset(client)
    payload = {
        "asset_id": asset["id"],
        "quantity": "1",
        "avg_buy_price": "100",
    }
    first_response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json=payload,
    )
    assert first_response.status_code == 201

    response = client.post(
        f"/api/v1/portfolios/{portfolio['id']}/positions",
        json=payload,
    )

    assert response.status_code == 400


def test_get_portfolio_summary_calculates_weights_and_threshold(
    client: TestClient,
) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client, concentration_threshold="0.6")
    apple = create_asset(client, "AAPL")
    microsoft = create_asset(client, "MSFT")
    add_position(
        client,
        portfolio["id"],
        apple["id"],
        quantity="3",
        avg_buy_price="100",
    )
    add_position(
        client,
        portfolio["id"],
        microsoft["id"],
        quantity="1",
        avg_buy_price="100",
    )

    response = client.get(f"/api/v1/portfolios/{portfolio['id']}/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["portfolio_id"] == portfolio["id"]
    assert Decimal(data["concentration_threshold"]) == Decimal("0.6")
    assert Decimal(data["total_cost_value"]) == Decimal("400.000000000000")
    positions = data["positions"]
    assert len(positions) == 2
    assert Decimal(positions[0]["cost_value"]) == Decimal("300.000000000000")
    assert Decimal(positions[0]["weight"]) == Decimal("0.75")
    assert positions[0]["exceeds_threshold"] is True
    assert Decimal(positions[1]["cost_value"]) == Decimal("100.000000000000")
    assert Decimal(positions[1]["weight"]) == Decimal("0.25")
    assert positions[1]["exceeds_threshold"] is False


def test_get_portfolio_summary_returns_zero_weights_without_positions(
    client: TestClient,
) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)

    response = client.get(f"/api/v1/portfolios/{portfolio['id']}/summary")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert Decimal(data["total_cost_value"]) == Decimal("0")
    assert data["positions"] == []


def test_check_concentration_creates_risk_alert_signal(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client, concentration_threshold="0.6")
    apple = create_asset(client, "AAPL")
    microsoft = create_asset(client, "MSFT")
    add_position(client, portfolio["id"], apple["id"], quantity="3", avg_buy_price="100")
    add_position(
        client,
        portfolio["id"],
        microsoft["id"],
        quantity="1",
        avg_buy_price="100",
    )

    response = client.post(f"/api/v1/portfolios/{portfolio['id']}/check")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert Decimal(data["summary"]["positions"][0]["weight"]) == Decimal("0.75")
    created_signals = data["created_signals"]
    assert len(created_signals) == 1
    signal = created_signals[0]
    assert signal["asset_id"] == apple["id"]
    assert signal["signal_type"] == "RISK_ALERT"
    assert signal["score"] == 75
    assert signal["risk_level"] == "HIGH"
    assert signal["evidence"]["portfolio_id"] == portfolio["id"]
    assert Decimal(signal["evidence"]["weight"]) == Decimal("0.75")
    assert Decimal(signal["evidence"]["threshold"]) == Decimal("0.6000")
    assert Decimal(signal["evidence"]["cost_value"]) == Decimal("300.000000000000")


def test_check_concentration_does_not_duplicate_active_signal(
    client: TestClient,
) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client, concentration_threshold="0.6")
    apple = create_asset(client, "AAPL")
    microsoft = create_asset(client, "MSFT")
    add_position(client, portfolio["id"], apple["id"], quantity="3", avg_buy_price="100")
    add_position(
        client,
        portfolio["id"],
        microsoft["id"],
        quantity="1",
        avg_buy_price="100",
    )

    first_response = client.post(f"/api/v1/portfolios/{portfolio['id']}/check")
    second_response = client.post(f"/api/v1/portfolios/{portfolio['id']}/check")

    assert first_response.status_code == 200
    first_data = cast(dict[str, Any], api_data(first_response))
    second_data = cast(dict[str, Any], api_data(second_response))
    assert len(first_data["created_signals"]) == 1
    assert second_response.status_code == 200
    assert second_data["created_signals"] == []


def test_check_concentration_does_not_create_signal_below_threshold(
    client: TestClient,
) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client, concentration_threshold="0.8")
    apple = create_asset(client, "AAPL")
    microsoft = create_asset(client, "MSFT")
    add_position(client, portfolio["id"], apple["id"], quantity="3", avg_buy_price="100")
    add_position(
        client,
        portfolio["id"],
        microsoft["id"],
        quantity="1",
        avg_buy_price="100",
    )

    response = client.post(f"/api/v1/portfolios/{portfolio['id']}/check")

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["created_signals"] == []


def test_summary_ownership_and_missing_paths(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    set_current_user(2, "other@example.com")

    forbidden_response = client.get(f"/api/v1/portfolios/{portfolio['id']}/summary")
    missing_response = client.get("/api/v1/portfolios/999/summary")

    assert forbidden_response.status_code == 403
    assert missing_response.status_code == 404


def test_check_ownership_and_missing_paths(client: TestClient) -> None:
    set_current_user(1)
    portfolio = create_portfolio(client)
    set_current_user(2, "other@example.com")

    forbidden_response = client.post(f"/api/v1/portfolios/{portfolio['id']}/check")
    missing_response = client.post("/api/v1/portfolios/999/check")

    assert forbidden_response.status_code == 403
    assert missing_response.status_code == 404
