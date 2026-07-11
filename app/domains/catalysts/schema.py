from datetime import date
from enum import Enum

from pydantic import BaseModel


class CatalystEventType(str, Enum):
    EARNINGS = "EARNINGS"
    PRODUCT = "PRODUCT"
    SHAREHOLDER_MEETING = "SHAREHOLDER_MEETING"
    DIVIDEND = "DIVIDEND"
    REGULATORY = "REGULATORY"
    CONTRACT = "CONTRACT"
    LOCKUP = "LOCKUP"
    CONFERENCE = "CONFERENCE"
    ECONOMIC = "ECONOMIC"
    OTHER = "OTHER"


class CatalystEventProjection(BaseModel):
    event_date: date
    title: str
    event_type: CatalystEventType
    is_estimated: bool


class CatalystTimelineResponse(BaseModel):
    asset_id: int
    events: list[CatalystEventProjection]
