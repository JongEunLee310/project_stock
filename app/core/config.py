from typing import Annotated, Any, Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    APP_ENV: Literal["dev", "test", "prod"] = "dev"
    DATABASE_URL: str = "postgresql://postgres:postgres@localhost:5432/stock_db"
    REDIS_URL: str = "redis://localhost:6379/0"
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_MINUTES: int = 2880
    OPENAI_API_KEY: str | None = None
    OPENAI_BASE_URL: str | None = None
    OPENAI_MODEL: str = "gpt-5.5"
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_PROVIDER: Literal["cloud", "local", "mock"] = "cloud"
    LLM_DAILY_CALL_LIMIT: int | None = None
    LLM_CACHE_TTL_SECONDS: int | None = None
    LLM_ESCALATION_ENABLED: bool = False
    LLM_ESCALATION_CONFIDENCE_THRESHOLD: float | None = None
    MARKET_PROVIDER: Literal["mock", "real", "yfinance"] = "mock"
    NEWS_PROVIDER: Literal["mock", "real", "rss"] = "mock"
    NEWS_QUERY_URL_TEMPLATE: str = (
        "https://news.google.com/rss/search?q={query}&hl={hl}&gl={gl}&ceid={gl}:{hl}"
    )
    DISCLOSURE_PROVIDER: Literal["mock", "real"] = "mock"
    PORTFOLIO_PROVIDER: Literal["mock", "real"] = "mock"
    CORS_ORIGINS: Annotated[list[str], NoDecode] = []
    CORS_ALLOW_CREDENTIALS: bool = False

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str] | Any:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    @field_validator(
        "LLM_DAILY_CALL_LIMIT",
        "LLM_CACHE_TTL_SECONDS",
        "LLM_ESCALATION_CONFIDENCE_THRESHOLD",
        mode="before",
    )
    @classmethod
    def parse_optional_number(cls, value: Any) -> int | float | None | Any:
        if value == "":
            return None
        return value

    @field_validator("OPENAI_BASE_URL", mode="before")
    @classmethod
    def parse_optional_string(cls, value: Any) -> str | None | Any:
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return None
        return value

    @field_validator("LLM_CACHE_TTL_SECONDS")
    @classmethod
    def validate_llm_cache_ttl_seconds(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("LLM_CACHE_TTL_SECONDS must be greater than 0")
        return value

    @field_validator("LLM_ESCALATION_CONFIDENCE_THRESHOLD")
    @classmethod
    def validate_llm_escalation_confidence_threshold(
        cls,
        value: float | None,
    ) -> float | None:
        if value is not None and (value <= 0.0 or value > 1.0):
            raise ValueError(
                "LLM_ESCALATION_CONFIDENCE_THRESHOLD must be greater than 0.0 "
                "and less than or equal to 1.0"
            )
        return value

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> "Settings":
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=true cannot be used with CORS_ORIGINS=*"
            )
        return self


settings = Settings()
