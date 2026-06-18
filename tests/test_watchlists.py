from collections.abc import Generator
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


def create_watchlist(
    client: TestClient, name: str = "Core"
) -> dict[str, Any]:
    response = client.post("/api/v1/watchlists", json={"name": name})
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


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
    assert response.json() == [owner_watchlist]


def test_add_watchlist_item_success(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)

    response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": asset["id"], "priority": 10},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["watchlist_id"] == watchlist["id"]
    assert data["asset_id"] == asset["id"]
    assert data["priority"] == 10
    assert "created_at" in data


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


def test_remove_watchlist_item_success(client: TestClient) -> None:
    set_current_user(1)
    watchlist = create_watchlist(client)
    asset = create_asset(client)
    create_response = client.post(
        f"/api/v1/watchlists/{watchlist['id']}/items",
        json={"asset_id": asset["id"], "priority": 0},
    )
    assert create_response.status_code == 201
    item = create_response.json()

    response = client.delete(
        f"/api/v1/watchlists/{watchlist['id']}/items/{item['id']}",
    )

    assert response.status_code == 204
    assert response.content == b""


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
