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
    LLM_TIMEOUT_SECONDS: int = 30
    LLM_PROVIDER: Literal["cloud", "local", "mock"] = "cloud"
    MARKET_PROVIDER: Literal["mock", "real"] = "mock"
    NEWS_PROVIDER: Literal["mock", "real"] = "mock"
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

    @model_validator(mode="after")
    def validate_cors_credentials(self) -> "Settings":
        if self.CORS_ALLOW_CREDENTIALS and "*" in self.CORS_ORIGINS:
            raise ValueError(
                "CORS_ALLOW_CREDENTIALS=true cannot be used with CORS_ORIGINS=*"
            )
        return self


settings = Settings()
