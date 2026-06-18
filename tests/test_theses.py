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


def thesis_payload(asset_id: int, summary: str = "Long-term compounder") -> dict[str, Any]:
    return {
        "asset_id": asset_id,
        "summary": summary,
        "risk_factors": "Margin compression",
        "invalidation_conditions": "Revenue growth below 5%",
    }


def create_thesis(
    client: TestClient,
    asset_id: int,
    summary: str = "Long-term compounder",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/theses",
        json=thesis_payload(asset_id, summary),
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def test_create_thesis_success(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)

    data = create_thesis(client, asset["id"])

    assert data["id"] == 1
    assert data["user_id"] == 1
    assert data["asset_id"] == asset["id"]
    assert data["summary"] == "Long-term compounder"
    assert data["risk_factors"] == "Margin compression"
    assert data["invalidation_conditions"] == "Revenue growth below 5%"
    assert data["is_active"] is True
    assert "created_at" in data


def test_update_thesis_success(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    thesis = create_thesis(client, asset["id"])

    response = client.put(
        f"/api/v1/theses/{thesis['id']}",
        json={
            "summary": "Updated thesis",
            "risk_factors": None,
            "invalidation_conditions": "Breaks below cash-flow target",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == "Updated thesis"
    assert data["risk_factors"] is None
    assert data["invalidation_conditions"] == "Breaks below cash-flow target"


def test_get_latest_thesis_returns_latest_active_for_user(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    create_thesis(client, asset["id"], "Older thesis")
    latest = create_thesis(client, asset["id"], "Newer thesis")

    response = client.get(
        "/api/v1/theses/latest",
        params={"asset_id": asset["id"]},
    )

    assert response.status_code == 200
    assert response.json() == latest


def test_deactivate_thesis_success_and_excludes_from_latest(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    thesis = create_thesis(client, asset["id"])

    response = client.patch(f"/api/v1/theses/{thesis['id']}/deactivate")

    assert response.status_code == 200
    assert response.json()["is_active"] is False
    latest_response = client.get(
        "/api/v1/theses/latest",
        params={"asset_id": asset["id"]},
    )
    assert latest_response.status_code == 404


def test_thesis_ownership_blocks_other_users(client: TestClient) -> None:
    set_current_user(1)
    asset = create_asset(client)
    thesis = create_thesis(client, asset["id"])
    set_current_user(2, "other@example.com")

    response = client.put(
        f"/api/v1/theses/{thesis['id']}",
        json={"summary": "Attempted takeover"},
    )

    assert response.status_code == 403
