from datetime import date
from decimal import Decimal
from enum import Enum

from pydantic import BaseModel


class AssetEventRange(str, Enum):
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    ONE_YEAR = "1Y"


class AssetEventType(str, Enum):
    EARNINGS = "EARNINGS"


class AssetEventProjection(BaseModel):
    event_date: date
    event_type: AssetEventType
    eps_actual: Decimal | None
    eps_estimate: Decimal | None
    eps_surprise_percent: Decimal | None


class AssetEventHistoryResponse(BaseModel):
    asset_id: int
    range: AssetEventRange
    events: list[AssetEventProjection]
