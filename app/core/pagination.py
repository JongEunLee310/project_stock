import base64
import binascii
import json
from collections.abc import Callable, Collection
from dataclasses import dataclass
from datetime import UTC, datetime
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


@dataclass(frozen=True)
class DateTimeCursor:
    timestamp: datetime
    row_id: int


def encode_datetime_cursor(timestamp: datetime, row_id: int) -> str:
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    payload = json.dumps(
        {"timestamp": timestamp.astimezone(UTC).isoformat(), "row_id": row_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def decode_datetime_cursor(cursor: str) -> DateTimeCursor:
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.b64decode(cursor + padding, altchars=b"-_", validate=True))
        timestamp = datetime.fromisoformat(payload["timestamp"])
        row_id = payload["row_id"]
        if timestamp.tzinfo is None or not isinstance(row_id, int) or row_id < 1:
            raise ValueError
    except (binascii.Error, json.JSONDecodeError, KeyError, TypeError, ValueError):
        raise RequestValidationError(
            [
                {
                    "type": "value_error",
                    "loc": ("query", "cursor"),
                    "msg": "Invalid cursor",
                    "input": cursor,
                    "ctx": {"error": ValueError("Invalid cursor")},
                }
            ]
        ) from None
    return DateTimeCursor(timestamp=timestamp.astimezone(UTC), row_id=row_id)


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
