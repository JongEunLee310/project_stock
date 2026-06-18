from fastapi import Request
from fastapi.responses import JSONResponse


class AppException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail


async def app_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(exc, AppException):
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    return JSONResponse(status_code=500, content={"detail": "서버 오류가 발생했습니다."})
