from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.error_codes import ErrorCode

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    size: int
    total: int


class ApiResponse(BaseModel, Generic[T]):
    data: T | None = None
    message: str | None = None
    error: dict[str, Any] | None = None
    meta: PageMeta | None = None


def success(data: T, message: str | None = None) -> ApiResponse[T]:
    return ApiResponse(data=data, message=message)


def paginated(
    items: list[T],
    page: int,
    size: int,
    total: int,
) -> ApiResponse[list[T]]:
    return ApiResponse(
        data=items,
        meta=PageMeta(page=page, size=size, total=total),
    )


def error_response(
    code: ErrorCode,
    message: str,
    fields: list[dict[str, Any]] | None = None,
) -> ApiResponse[None]:
    error: dict[str, Any] = {"code": code.value}
    if fields is not None:
        error["fields"] = fields
    return ApiResponse(data=None, message=message, error=error, meta=None)
