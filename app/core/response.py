from typing import Any, Generic, TypeVar

from pydantic import BaseModel

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
