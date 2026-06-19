from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from tests.conftest import api_data, api_error


pytestmark = pytest.mark.usefixtures("stable_password_hashing")


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
    return cast(dict[str, Any], api_data(response))


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
    return cast(dict[str, Any], api_data(response))


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

    assert response.status_code == 400
    assert api_error(response) == {
        "code": "USER_EMAIL_DUPLICATE",
        "message": "이미 등록된 이메일입니다.",
    }


def test_register_user_rejects_invalid_email(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "correct-password"},
    )

    assert response.status_code == 422
    error = api_error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "요청 값이 올바르지 않습니다."
    assert any(
        field["loc"] == ["body", "email"]
        and field["msg"].startswith("value is not a valid email address")
        for field in error["fields"]
    )


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
    assert api_error(response) == {
        "code": "AUTH_INVALID_CREDENTIALS",
        "message": "이메일 또는 비밀번호가 올바르지 않습니다.",
    }


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
    data = cast(dict[str, Any], api_data(response))
    assert data["id"] == user["id"]
    assert data["email"] == "owner@example.com"


def test_get_me_requires_authorization_header(client: TestClient) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert api_error(response) == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "유효하지 않은 토큰입니다.",
    }
    assert response.headers["www-authenticate"] == "Bearer"


def test_get_me_rejects_tampered_token(client: TestClient) -> None:
    register_user(client)
    token = login_user(client)["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}tampered"},
    )

    assert response.status_code == 401
    assert api_error(response) == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "유효하지 않은 토큰입니다.",
    }
    assert response.headers["www-authenticate"] == "Bearer"
