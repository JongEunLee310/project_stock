from datetime import UTC, datetime
from typing import Annotated

from pydantic import PlainSerializer


def serialize_utc(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


UtcDatetime = Annotated[
    datetime, PlainSerializer(serialize_utc, return_type=str, when_used="json")
]
