from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ProcessingStatus(str, Enum):
    FETCHED = "fetched"
    NORMALIZED = "normalized"
    FAILED = "failed"
    SKIPPED_DUPLICATE = "skipped_duplicate"


class DataQualityStatus(str, Enum):
    VALID = "valid"
    INVALID = "invalid"
    STALE = "stale"
    DUPLICATE = "duplicate"
    LOW_TRUST = "low_trust"


class ValidationErrorReason(str, Enum):
    MISSING_REQUIRED_FIELD = "missing_required_field"
    FUTURE_TIMESTAMP = "future_timestamp"
    STALE = "stale"
    NEGATIVE_PRICE = "negative_price"
    HIGH_LOW_INVERTED = "high_low_inverted"
    CURRENCY_MISMATCH = "currency_mismatch"
    OUTLIER_RETURN = "outlier_return"


class RawDataType(str, Enum):
    PRICE = "price"
    NEWS = "news"


class RawProviderResponse(BaseModel):
    provider: str
    data_type: RawDataType
    symbol: str | None = None
    market: str | None = None
    payload: dict[str, Any]
    payload_hash: str = Field(max_length=64)
    fetched_at: datetime
    processing_status: ProcessingStatus = ProcessingStatus.FETCHED
