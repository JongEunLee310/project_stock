from pathlib import Path
from typing import Any, cast

import pytest

from app.core.config import Settings


def _settings_without_env_file() -> Settings:
    settings_cls = cast(Any, Settings)
    return cast(Settings, settings_cls(_env_file=None))


def _clear_settings_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for field_name in Settings.model_fields:
        monkeypatch.delenv(field_name, raising=False)


def test_settings_use_defaults_without_env_file(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)

    settings = _settings_without_env_file()

    assert settings.APP_ENV == "dev"
    assert settings.DATABASE_URL == "postgresql://postgres:postgres@localhost:5432/stock_db"
    assert settings.REDIS_URL == "redis://localhost:6379/0"
    assert settings.SECRET_KEY == "change-me-in-production"
    assert settings.ALGORITHM == "HS256"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 15
    assert settings.REFRESH_TOKEN_EXPIRE_MINUTES == 2880
    assert settings.OPENAI_API_KEY is None
    assert settings.LLM_TIMEOUT_SECONDS == 30
    assert settings.LLM_PROVIDER == "cloud"
    assert settings.MARKET_PROVIDER == "mock"
    assert settings.NEWS_PROVIDER == "mock"
    assert settings.DISCLOSURE_PROVIDER == "mock"
    assert settings.PORTFOLIO_PROVIDER == "mock"
    assert settings.CORS_ORIGINS == []
    assert settings.CORS_ALLOW_CREDENTIALS is False


def test_settings_load_values_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost:5432/test_db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6380/1")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ALGORITHM", "HS512")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "45")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "12")
    monkeypatch.setenv("LLM_PROVIDER", "local")
    monkeypatch.setenv("MARKET_PROVIDER", "real")
    monkeypatch.setenv("NEWS_PROVIDER", "real")
    monkeypatch.setenv("DISCLOSURE_PROVIDER", "real")
    monkeypatch.setenv("PORTFOLIO_PROVIDER", "real")
    monkeypatch.setenv("CORS_ORIGINS", "http://localhost:3000, http://localhost:5173")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    settings = _settings_without_env_file()

    assert settings.APP_ENV == "test"
    assert settings.DATABASE_URL == "postgresql://user:pass@localhost:5432/test_db"
    assert settings.REDIS_URL == "redis://localhost:6380/1"
    assert settings.SECRET_KEY == "test-secret"
    assert settings.ALGORITHM == "HS512"
    assert settings.ACCESS_TOKEN_EXPIRE_MINUTES == 45
    assert settings.OPENAI_API_KEY == "test-openai-key"
    assert settings.LLM_TIMEOUT_SECONDS == 12
    assert settings.LLM_PROVIDER == "local"
    assert settings.MARKET_PROVIDER == "real"
    assert settings.NEWS_PROVIDER == "real"
    assert settings.DISCLOSURE_PROVIDER == "real"
    assert settings.PORTFOLIO_PROVIDER == "real"
    assert settings.CORS_ORIGINS == [
        "http://localhost:3000",
        "http://localhost:5173",
    ]
    assert settings.CORS_ALLOW_CREDENTIALS is True


def test_settings_accept_yfinance_market_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("MARKET_PROVIDER", "yfinance")

    settings = _settings_without_env_file()

    assert settings.MARKET_PROVIDER == "yfinance"


def test_settings_reject_wildcard_origin_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_settings_env(monkeypatch)
    monkeypatch.setenv("CORS_ORIGINS", "*")
    monkeypatch.setenv("CORS_ALLOW_CREDENTIALS", "true")

    with pytest.raises(ValueError, match="CORS_ALLOW_CREDENTIALS"):
        _settings_without_env_file()


def test_env_example_keys_match_settings_fields() -> None:
    env_example = Path(".env.example")
    example_keys = {
        line.split("=", maxsplit=1)[0]
        for line in env_example.read_text().splitlines()
        if line and not line.startswith("#")
    }

    assert example_keys == set(Settings.model_fields)
