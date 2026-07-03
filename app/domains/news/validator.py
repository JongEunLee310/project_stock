from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.domains.ingestion.schema import DataQualityStatus, ValidationErrorReason
from app.domains.news.schema import NewsItemCreate

_STALE_AFTER_DAYS = 30


@dataclass(frozen=True)
class NewsValidationOutcome:
    status: DataQualityStatus
    reasons: list[ValidationErrorReason]


class NewsValidator:
    def validate(
        self,
        data: NewsItemCreate,
        *,
        now: datetime,
    ) -> NewsValidationOutcome:
        reasons: list[ValidationErrorReason] = []
        if _is_blank(data.title) or _is_blank(data.url) or _is_blank(data.source):
            reasons.append(ValidationErrorReason.MISSING_REQUIRED_FIELD)

        normalized_now = _as_utc(now)
        published_at = (
            _as_utc(data.published_at) if data.published_at is not None else None
        )
        if published_at is not None and published_at > normalized_now:
            reasons.append(ValidationErrorReason.FUTURE_TIMESTAMP)

        if reasons:
            return NewsValidationOutcome(
                status=DataQualityStatus.INVALID,
                reasons=reasons,
            )

        if (
            published_at is not None
            and normalized_now - published_at > timedelta(days=_STALE_AFTER_DAYS)
        ):
            return NewsValidationOutcome(
                status=DataQualityStatus.STALE,
                reasons=[ValidationErrorReason.STALE],
            )

        return NewsValidationOutcome(status=DataQualityStatus.VALID, reasons=[])


def _is_blank(value: str) -> bool:
    return value.strip() == ""


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
