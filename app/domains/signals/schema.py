import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.schema import UtcDatetime

from app.domains.signals.time import is_expired_at
from app.domains.signals.types import SignalType
from app.domains.watchlists.schema import AssetBriefResponse


class SignalCreate(BaseModel):
    asset_id: int
    thesis_id: int | None = None
    news_item_id: int | None = None
    signal_type: SignalType
    score: int = Field(ge=0, le=100)
    risk_level: str | None = Field(default=None, max_length=20)
    reason: str
    evidence: dict[str, Any] | None = None
    expires_at: datetime | None = None


class SignalResponse(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    asset_id: int
    thesis_id: int | None
    news_item_id: int | None
    signal_type: str
    score: int
    risk_level: str | None
    reason: str
    evidence: dict[str, Any] | None
    expires_at: UtcDatetime | None
    is_expired: bool = False
    created_at: UtcDatetime

    @field_validator("evidence", mode="before")
    @classmethod
    def parse_evidence(cls, value: Any) -> Any:
        if value is None or isinstance(value, dict):
            return value
        if isinstance(value, str):
            return json.loads(value)
        return value

    @model_validator(mode="after")
    def calculate_is_expired(self) -> "SignalResponse":
        self.is_expired = is_expired_at(self.expires_at)
        return self


class SignalExpandedResponse(SignalResponse):
    asset: AssetBriefResponse | None = None
