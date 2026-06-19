from datetime import datetime, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def is_expired_at(expires_at: datetime | None, now: datetime | None = None) -> bool:
    if expires_at is None:
        return False
    reference = now or utc_now()
    return as_utc(expires_at) <= as_utc(reference)
