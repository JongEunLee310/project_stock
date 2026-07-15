from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.schema import UtcDatetime
from app.domains.alert_rules.types import (
    AlertChannel,
    AlertDeliveryPolicy,
    AlertSeverity,
    AlertTargetType,
    AlertTemplateType,
)


AlertRuleStatus = Literal["ACTIVE", "PAUSED"]


class AlertRuleCreate(BaseModel):
    template_type: AlertTemplateType
    target_id: str | None = Field(default=None, max_length=255)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    condition: dict[str, Any] | None = None
    severity: AlertSeverity | None = None
    channels: list[AlertChannel] | None = Field(default=None, min_length=1)
    enabled: bool = True
    cooldown_seconds: int | None = Field(default=None, ge=0)
    delivery_policy: AlertDeliveryPolicy | None = None


class AlertRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    target_type: AlertTargetType | None = None
    target_id: str | None = Field(default=None, max_length=255)
    condition: dict[str, Any] | None = None
    severity: AlertSeverity | None = None
    channels: list[AlertChannel] | None = Field(default=None, min_length=1)
    enabled: bool | None = None
    cooldown_seconds: int | None = Field(default=None, ge=0)
    delivery_policy: AlertDeliveryPolicy | None = None

    @model_validator(mode="after")
    def reject_null_for_non_nullable_fields(self) -> "AlertRuleUpdate":
        nullable_fields = {"target_id"}
        for field in self.model_fields_set - nullable_fields:
            if getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class AlertRuleProjection(BaseModel):
    model_config = {"from_attributes": True}

    id: int
    user_id: int
    name: str
    source: str
    template_type: str | None
    target_type: str
    target_id: str | None
    condition: dict[str, Any]
    severity: str
    channels: list[str]
    enabled: bool
    status: AlertRuleStatus
    cooldown_seconds: int
    delivery_policy: str
    last_triggered_at: UtcDatetime | None
    created_at: UtcDatetime
    updated_at: UtcDatetime


class AlertRuleTemplateProjection(BaseModel):
    template_type: AlertTemplateType
    label: str
    target_type: AlertTargetType
    condition: dict[str, Any]
    severity: AlertSeverity
    channels: list[AlertChannel]
    cooldown_seconds: int
    delivery_policy: AlertDeliveryPolicy
    is_active: bool


class AlertOverviewProjection(BaseModel):
    active_rule_count: int
    triggered_today_count: int
    high_severity_count: int
    paused_rule_count: int
    unread_count: int
    as_of: UtcDatetime
