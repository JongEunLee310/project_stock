from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.core.config import settings
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
    assert data["username"] == "owner"
    assert data["is_active"] is True
    assert "created_at" in data
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
    assert data["refresh_token"]
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60


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
    assert data["username"] == "owner"
    assert "created_at" in data


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


# --- refresh 토큰 테스트 ---


def test_refresh_returns_new_access_token(client: TestClient) -> None:
    register_user(client)
    tokens = login_user(client)
    refresh_token = tokens["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["access_token"]
    assert data["token_type"] == "bearer"
    assert isinstance(data["expires_in"], int)
    assert data["expires_in"] == settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    # 비회전 정책: refresh 응답의 refresh_token은 빈 문자열(갱신 없음)
    assert not data.get("refresh_token")


def test_refresh_rejects_tampered_token(client: TestClient) -> None:
    register_user(client)
    tokens = login_user(client)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"] + "tampered"},
    )

    assert response.status_code == 401
    assert api_error(response) == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "유효하지 않은 토큰입니다.",
    }


def test_refresh_rejects_expired_token(client: TestClient) -> None:
    register_user(client)

    # 이미 만료된 토큰을 직접 생성
    expired_payload = {
        "sub": "1",
        "type": "refresh",
        "exp": datetime.now(UTC) - timedelta(seconds=1),
    }
    expired_token = jwt.encode(expired_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": expired_token},
    )

    assert response.status_code == 401
    assert api_error(response)["code"] == "AUTH_INVALID_TOKEN"


def test_refresh_rejects_access_token(client: TestClient) -> None:
    """access 토큰을 refresh 엔드포인트에 제시하면 401"""
    register_user(client)
    tokens = login_user(client)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )

    assert response.status_code == 401
    assert api_error(response)["code"] == "AUTH_INVALID_TOKEN"


def test_refresh_rejects_nonexistent_user(client: TestClient) -> None:
    """존재하지 않는 사용자 ID의 refresh 토큰 → 401"""
    nonexistent_payload = {
        "sub": "999999",
        "type": "refresh",
        "exp": datetime.now(UTC) + timedelta(days=1),
    }
    token = jwt.encode(nonexistent_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": token},
    )

    assert response.status_code == 401
    assert api_error(response)["code"] == "AUTH_INVALID_TOKEN"


def test_get_me_rejects_refresh_token(client: TestClient) -> None:
    """refresh 토큰으로 보호 API(/auth/me) 접근 시 401"""
    register_user(client)
    tokens = login_user(client)
    refresh_token = tokens["refresh_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {refresh_token}"},
    )

    assert response.status_code == 401
    assert api_error(response)["code"] == "AUTH_INVALID_TOKEN"


def test_get_me_accepts_access_token(client: TestClient) -> None:
    """access 토큰으로 보호 API는 정상 접근"""
    register_user(client)
    tokens = login_user(client)
    access_token = tokens["access_token"]

    response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    assert response.status_code == 200
