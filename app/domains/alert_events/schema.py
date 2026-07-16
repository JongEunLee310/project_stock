from typing import Annotated, Any

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime


AlertEventId = Annotated[int, Field(gt=0)]


class AlertEventProjection(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    rule_id: int
    user_id: int
    target_type: str
    target_id: str | None
    asset_id: int | None
    title: str
    message: str
    severity: str
    read_at: UtcDatetime | None
    triggered_at: UtcDatetime


class AlertEventDetailProjection(AlertEventProjection):
    triggered_value: dict[str, Any]
    evidence: list[dict[str, Any]]


class AlertEventReadRequest(BaseModel):
    alert_ids: list[AlertEventId] = Field(min_length=1)
