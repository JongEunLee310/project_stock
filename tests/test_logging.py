import logging
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.core.logging import MASKED_VALUE, mask_sensitive
from app.main import create_app


def _settings_without_env_file(**values: Any) -> Settings:
    settings_cls = cast(Any, Settings)
    return cast(Settings, settings_cls(_env_file=None, **values))


def test_request_id_is_propagated_to_response_and_request_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(_settings_without_env_file(APP_ENV="test"))
    caplog.set_level(logging.INFO, logger="app.request")

    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "trace-123"})

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "trace-123"

    request_records = [
        record for record in caplog.records if record.name == "app.request"
    ]
    assert request_records
    assert getattr(request_records[-1], "request_id") == "trace-123"
    assert getattr(request_records[-1], "method") == "GET"
    assert getattr(request_records[-1], "path") == "/health"
    assert getattr(request_records[-1], "status_code") == 200
    assert isinstance(getattr(request_records[-1], "latency_ms"), float)


def test_request_id_is_generated_when_header_is_missing() -> None:
    app = create_app(_settings_without_env_file(APP_ENV="test"))

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Request-ID"]


def test_app_exception_logs_request_context(caplog: pytest.LogCaptureFixture) -> None:
    app = create_app(_settings_without_env_file(APP_ENV="test"))

    @app.get("/app-error")
    def app_error() -> None:
        raise AppException(
            status_code=409,
            detail="conflict",
            error_code=ErrorCode.ASSET_DUPLICATE,
        )

    caplog.set_level(logging.WARNING, logger="app.core.exceptions")

    with TestClient(app) as client:
        response = client.get("/app-error", headers={"X-Request-ID": "trace-app"})

    assert response.status_code == 409
    assert response.headers["X-Request-ID"] == "trace-app"

    error_record = next(
        record
        for record in caplog.records
        if record.name == "app.core.exceptions"
    )
    assert getattr(error_record, "request_id") == "trace-app"
    assert getattr(error_record, "path") == "/app-error"
    assert getattr(error_record, "status_code") == 409
    assert getattr(error_record, "error_code") == "ASSET_DUPLICATE"


def test_unhandled_exception_logs_stack_and_request_context(
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = create_app(_settings_without_env_file(APP_ENV="test"))

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password leaked")

    caplog.set_level(logging.ERROR, logger="app.core.exceptions")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/boom", headers={"X-Request-ID": "trace-boom"})

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == "trace-boom"

    error_record = next(
        record
        for record in caplog.records
        if record.name == "app.core.exceptions"
    )
    assert getattr(error_record, "request_id") == "trace-boom"
    assert getattr(error_record, "path") == "/boom"
    assert error_record.exc_info is not None


def test_mask_sensitive_masks_nested_secret_values() -> None:
    payload = {
        "SECRET_KEY": "secret",
        "Authorization": "Bearer token",
        "nested": {
            "openai_api_key": "sk-test",
            "normal": "visible",
        },
        "items": [{"refresh_token": "refresh"}],
    }

    assert mask_sensitive(payload) == {
        "SECRET_KEY": MASKED_VALUE,
        "Authorization": MASKED_VALUE,
        "nested": {
            "openai_api_key": MASKED_VALUE,
            "normal": "visible",
        },
        "items": [{"refresh_token": MASKED_VALUE}],
    }
