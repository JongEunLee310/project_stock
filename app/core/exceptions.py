import logging
from contextvars import Token

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.error_codes import ErrorCode
from app.core.logging import REQUEST_ID_HEADER, reset_request_id, set_request_id
from app.core.response import error_response

logger = logging.getLogger(__name__)


class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        detail: str,
        error_code: ErrorCode,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.error_code = error_code
        self.headers = headers


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppException):
        return await unhandled_exception_handler(request, exc)
    token = _set_request_context_from_state(request)
    try:
        logger.warning(
            "application exception method=%s path=%s status_code=%s error_code=%s",
            request.method,
            request.url.path,
            exc.status_code,
            exc.error_code.value,
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
                "error_code": exc.error_code.value,
                "detail": exc.detail,
            },
        )
    finally:
        if token is not None:
            reset_request_id(token)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_response(
            code=exc.error_code,
            message=exc.detail,
        ).model_dump(),
        headers=_response_headers(request, exc.headers),
    )


async def validation_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        return await unhandled_exception_handler(request, exc)
    fields = [
        {
            "loc": list(error["loc"]),
            "msg": str(error["msg"]),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=error_response(
            code=ErrorCode.VALIDATION_ERROR,
            message="요청 값이 올바르지 않습니다.",
            fields=fields,
        ).model_dump(),
    )


async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    token = _set_request_context_from_state(request)
    try:
        logger.error(
            "unhandled exception method=%s path=%s",
            request.method,
            request.url.path,
            extra={
                "method": request.method,
                "path": request.url.path,
            },
            exc_info=(type(exc), exc, exc.__traceback__),
        )
    finally:
        if token is not None:
            reset_request_id(token)
    return JSONResponse(
        status_code=500,
        content=error_response(
            code=ErrorCode.INTERNAL_ERROR,
            message="서버 오류가 발생했습니다.",
        ).model_dump(),
        headers=_response_headers(request),
    )


def _response_headers(
    request: Request,
    headers: dict[str, str] | None = None,
) -> dict[str, str] | None:
    response_headers = dict(headers or {})
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        response_headers[REQUEST_ID_HEADER] = request_id
    return response_headers or None


def _set_request_context_from_state(request: Request) -> Token[str] | None:
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id:
        return set_request_id(request_id)
    return None
