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


def register_user(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = "correct-password",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password},
    )
    assert response.status_code == 201
    return cast(dict[str, Any], response.json())


def login_user(
    client: TestClient,
    email: str = "owner@example.com",
    password: str = "correct-password",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return cast(dict[str, Any], response.json())


def test_register_user_success(client: TestClient) -> None:
    data = register_user(client)

    assert data["email"] == "owner@example.com"
    assert data["is_active"] is True
    assert "id" in data


def test_register_user_rejects_duplicate_email(client: TestClient) -> None:
    register_user(client)

    response = client.post(
        "/api/v1/auth/register",
        json={"email": "owner@example.com", "password": "correct-password"},
    )

    assert 400 <= response.status_code < 500


def test_register_user_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "correct-password"},
    )

    assert response.status_code == 422


def test_login_user_success(client: TestClient) -> None:
    register_user(client)

    data = login_user(client)

    assert data["access_token"]
    assert data["token_type"] == "bearer"


def test_login_user_rejects_wrong_password(client: TestClient) -> None:
    register_user(client)

    response = client.post(
        "/api/v1/auth/login",
        json={"email": "owner@example.com", "password": "wrong-password"},
    )

    assert response.status_code == 401


def test_login_user_rejects_missing_user(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "missing@example.com", "password": "correct-password"},
    )

    assert response.status_code == 401


def test_get_me_with_bearer_token(client: TestClient) -> None:
    user = register_user(client)
    token = login_user(client)["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["id"] == user["id"]
    assert response.json()["email"] == "owner@example.com"


def test_get_me_requires_authorization_header(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401


def test_get_me_rejects_tampered_token(client: TestClient) -> None:
    register_user(client)
    token = login_user(client)["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}tampered"},
    )

    assert response.status_code == 401
