import json
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from app.domains.signals.types import SignalType


class SignalCreate(BaseModel):
    asset_id: int
    thesis_id: int | None = None
    news_item_id: int | None = None
    signal_type: SignalType
    score: int
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
    expires_at: datetime | None
    is_expired: bool = False
    created_at: datetime

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
        if self.expires_at is None:
            self.is_expired = False
            return self
        expires_at = self.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        self.is_expired = expires_at <= datetime.now(timezone.utc)
        return self
