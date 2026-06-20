from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Annotated, Literal

from fastapi import Query
from fastapi.exceptions import RequestValidationError


class PaginationParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1)] = 1,
        size: Annotated[int, Query(ge=1, le=100)] = 20,
    ) -> None:
        self.page = page
        self.size = size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.size

    @property
    def limit(self) -> int:
        return self.size


@dataclass(frozen=True)
class SortParams:
    field: str
    direction: Literal["asc", "desc"]

    @property
    def value(self) -> str:
        prefix = "-" if self.direction == "desc" else ""
        return f"{prefix}{self.field}"


def parse_sort(
    sort: str | None,
    *,
    allowed_fields: Collection[str],
    default: str,
) -> SortParams:
    raw_sort = sort or default
    direction: Literal["asc", "desc"] = "desc" if raw_sort.startswith("-") else "asc"
    field = raw_sort[1:] if direction == "desc" else raw_sort
    if field not in allowed_fields:
        allowed_values = sorted(
            value
            for allowed_field in allowed_fields
            for value in (allowed_field, f"-{allowed_field}")
        )
        raise RequestValidationError(
            [
                {
                    "loc": ("query", "sort"),
                    "msg": (
                        "Input should be one of: "
                        f"{', '.join(allowed_values)}"
                    ),
                }
            ]
        )
    return SortParams(field=field, direction=direction)


def sort_param(
    *,
    allowed_fields: Collection[str],
    default: str,
) -> Callable[[str | None], SortParams]:
    parse_sort(default, allowed_fields=allowed_fields, default=default)

    def dependency(
        sort: Annotated[str | None, Query()] = default,
    ) -> SortParams:
        return parse_sort(sort, allowed_fields=allowed_fields, default=default)

    return dependency
