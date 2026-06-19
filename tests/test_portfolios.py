from collections.abc import Generator
from decimal import Decimal
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.deps import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.domains.users.model import User
from app.main import app


engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    Base.metadata.create_all(bind=engine)

    def override_get_db() -> Generator[Session, None, None]:
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)


def set_current_user(user_id: int, email: str = "owner@example.com") -> None:
    def override_get_current_user() -> User:
        return User(id=user_id, email=email, hashed_password="test-hash")

    app.dependency_overrides[get_current_user] = override_get_current_user


def create_asset(client: TestClient, symbol: str = "AAPL") -> dict[str, Any]:
    response = client.post(
        "/api/v1/assets",
        json={"symbol": symbol, "name": f"{symbol} Inc.", "market": "NASDAQ"},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def create_portfolio(
    client: TestClient, name: str = "Long Term"
) -> dict[str, Any]:
    response = client.post("/api/v1/portfolios", json={"name": name})
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


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
    return cast(dict[str, Any], response.json())


def test_create_portfolio_success(client: TestClient) -> None:
    set_current_user(1)

    data = create_portfolio(client)

    assert data["id"] == 1
    assert data["user_id"] == 1
    assert data["name"] == "Long Term"
    assert "created_at" in data


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
    assert response.json() == [owner_portfolio]


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
    data = response.json()
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
    quantity_data = quantity_response.json()
    assert Decimal(quantity_data["quantity"]) == Decimal("15.25")
    assert Decimal(quantity_data["avg_buy_price"]) == Decimal("123.45")

    price_response = client.patch(
        f"/api/v1/portfolios/{portfolio['id']}/positions/{position['id']}",
        json={"avg_buy_price": "140.125"},
    )
    assert price_response.status_code == 200
    price_data = price_response.json()
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

    assert response.status_code == 204
    assert response.content == b""


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
