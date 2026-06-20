from fastapi.testclient import TestClient

from tests.conftest import api_error


def test_unauthenticated_request_returns_common_error_envelope(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/auth/me")

    assert response.status_code == 401
    assert api_error(response) == {
        "code": "AUTH_INVALID_TOKEN",
        "message": "유효하지 않은 토큰입니다.",
    }


def test_missing_resource_returns_common_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/assets/999")

    assert response.status_code == 404
    assert api_error(response) == {
        "code": "ASSET_NOT_FOUND",
        "message": "종목을 찾을 수 없습니다.",
    }


def test_validation_error_returns_common_error_envelope(client: TestClient) -> None:
    response = client.get("/api/v1/assets/not-an-int")

    assert response.status_code == 422
    error = api_error(response)
    assert error["code"] == "VALIDATION_ERROR"
    assert error["message"] == "요청 값이 올바르지 않습니다."
    assert {
        "loc": ["path", "asset_id"],
        "msg": "Input should be a valid integer, unable to parse string as an integer",
    } in error["fields"]
