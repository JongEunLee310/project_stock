import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

PACKAGE_NAME = "ai-assisted-fastapi-template"
PROJECT_ROOT = Path(__file__).resolve().parents[4]

router = APIRouter()


class DependencyCheck(BaseModel):
    status: Literal["ok", "error"]


class ProviderModes(BaseModel):
    market: Literal["mock", "real"]
    news: Literal["mock", "real"]
    disclosure: Literal["mock", "real"]
    portfolio: Literal["mock", "real"]


class ReadinessResponse(BaseModel):
    status: Literal["ok", "error"]
    checks: dict[str, DependencyCheck]
    providers: ProviderModes
    version: str


@router.get(
    "",
    summary="Health check",
    description="Return service health status without the common API envelope for monitoring compatibility.",
)
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get(
    "/readiness",
    response_model=ReadinessResponse,
    responses={503: {"model": ReadinessResponse}},
    summary="Readiness check",
    description="Return dependency readiness, provider modes, and application version.",
)
def readiness_check(db: Session = Depends(get_db)) -> ReadinessResponse | JSONResponse:
    providers = ProviderModes(
        market=settings.MARKET_PROVIDER,
        news=settings.NEWS_PROVIDER,
        disclosure=settings.DISCLOSURE_PROVIDER,
        portfolio=settings.PORTFOLIO_PROVIDER,
    )
    response = ReadinessResponse(
        status="ok",
        checks={"db": DependencyCheck(status="ok")},
        providers=providers,
        version=get_app_version(),
    )

    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status = "error"
        response.checks["db"] = DependencyCheck(status="error")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )

    return response


def get_app_version() -> str:
    try:
        return version(PACKAGE_NAME)
    except PackageNotFoundError:
        pyproject_path = PROJECT_ROOT / "pyproject.toml"
        with pyproject_path.open("rb") as pyproject_file:
            pyproject = tomllib.load(pyproject_file)
        return str(pyproject["project"]["version"])
