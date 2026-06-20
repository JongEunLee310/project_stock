from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import get_db
from app.main import app


def test_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_v1_health_check_returns_ok(client: TestClient) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_check_returns_dependency_and_runtime_info(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_mock_provider_modes(monkeypatch)
    response = client.get("/health/readiness")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "checks": {"db": {"status": "ok"}},
        "providers": {
            "market": "mock",
            "news": "mock",
            "disclosure": "mock",
            "portfolio": "mock",
        },
        "version": "0.1.0",
    }


def test_readiness_check_returns_503_when_db_check_fails(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    set_mock_provider_modes(monkeypatch)

    class FailingSession:
        def execute(self, _statement: object) -> None:
            raise SQLAlchemyError("database unavailable")

    def override_get_db() -> Generator[object, None, None]:
        yield FailingSession()

    app.dependency_overrides[get_db] = override_get_db
    response = client.get("/health/readiness")

    assert response.status_code == 503
    assert response.json() == {
        "status": "error",
        "checks": {"db": {"status": "error"}},
        "providers": {
            "market": "mock",
            "news": "mock",
            "disclosure": "mock",
            "portfolio": "mock",
        },
        "version": "0.1.0",
    }


def set_mock_provider_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "MARKET_PROVIDER", "mock")
    monkeypatch.setattr(settings, "NEWS_PROVIDER", "mock")
    monkeypatch.setattr(settings, "DISCLOSURE_PROVIDER", "mock")
    monkeypatch.setattr(settings, "PORTFOLIO_PROVIDER", "mock")
