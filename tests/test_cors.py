from typing import Any, cast

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _settings_without_env_file(**values: Any) -> Settings:
    settings_cls = cast(Any, Settings)
    return cast(Settings, settings_cls(_env_file=None, **values))


def test_allowed_origin_gets_cors_response_header() -> None:
    app = create_app(
        _settings_without_env_file(CORS_ORIGINS=["http://frontend.test"])
    )

    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://frontend.test"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://frontend.test"


def test_preflight_request_is_handled_by_cors_middleware() -> None:
    app = create_app(
        _settings_without_env_file(CORS_ORIGINS=["http://frontend.test"])
    )

    with TestClient(app) as client:
        response = client.options(
            "/health",
            headers={
                "Origin": "http://frontend.test",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://frontend.test"
    assert "GET" in response.headers["access-control-allow-methods"]


def test_disallowed_origin_does_not_get_cors_allow_origin_header() -> None:
    app = create_app(
        _settings_without_env_file(CORS_ORIGINS=["http://frontend.test"])
    )

    with TestClient(app) as client:
        response = client.get("/health", headers={"Origin": "http://other.test"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers
