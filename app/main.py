from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import Settings, settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.core.logging import setup_logging
from app.core.middleware import RequestIdMiddleware


def create_app(app_settings: Settings = settings) -> FastAPI:
    setup_logging(app_settings)
    application = FastAPI(title="Project Stock API")

    application.add_middleware(RequestIdMiddleware)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.CORS_ORIGINS,
        allow_credentials=app_settings.CORS_ALLOW_CREDENTIALS,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.add_exception_handler(AppException, app_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
    application.include_router(api_router)

    @application.get(
        "/health",
        tags=["health"],
        summary="Root health check",
        description="Return service health status without the common API envelope for monitoring compatibility.",
    )
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return application


app = create_app()
