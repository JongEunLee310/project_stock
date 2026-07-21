from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.core.error_codes import ErrorCode

T = TypeVar("T")


class PageMeta(BaseModel):
    page: int
    size: int
    total: int


class CursorPageMeta(BaseModel):
    limit: int
    has_more: bool
    next_cursor: str | None = None


class ApiResponse(BaseModel, Generic[T]):
    data: T | None = None
    message: str | None = None
    error: dict[str, Any] | None = None
    meta: PageMeta | CursorPageMeta | None = None


class PaginatedApiResponse(ApiResponse[list[T]], Generic[T]):
    meta: PageMeta


def success(data: T, message: str | None = None) -> ApiResponse[T]:
    return ApiResponse(data=data, message=message)


def paginated(
    items: list[T],
    page: int,
    size: int,
    total: int,
) -> PaginatedApiResponse[T]:
    return PaginatedApiResponse(
        data=items,
        meta=PageMeta(page=page, size=size, total=total),
    )


def cursor_paginated(
    items: list[T],
    *,
    limit: int,
    has_more: bool,
    next_cursor: str | None,
) -> ApiResponse[list[T]]:
    return ApiResponse(
        data=items,
        meta=CursorPageMeta(
            limit=limit,
            has_more=has_more,
            next_cursor=next_cursor,
        ),
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
