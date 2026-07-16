from typing import Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime
from app.domains.alert_rules.types import AlertChannel


class NotificationChannelCreate(BaseModel):
    channel_type: AlertChannel
    configuration: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelProjection(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    channel_type: str
    configuration: dict[str, Any]
    enabled: bool
    verified_at: UtcDatetime | None
