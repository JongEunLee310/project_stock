from datetime import UTC, datetime
from math import isfinite
from numbers import Real
from typing import Any

from sqlalchemy.orm import Session

from app.core.error_codes import ErrorCode
from app.core.exceptions import AppException
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.repository import AlertRuleRepository
from app.domains.alert_rules.schema import (
    AlertOverviewProjection,
    AlertRuleCreate,
    AlertRuleProjection,
    AlertRuleTemplateProjection,
    AlertRuleUpdate,
)
from app.domains.alert_rules.types import (
    AlertChannel,
    AlertDeliveryPolicy,
    AlertMetric,
    AlertOperator,
    AlertRuleSource,
    AlertSeverity,
    AlertTargetType,
    AlertTemplateType,
)
from app.domains.watchlists.types import NewsRisk, ThemeHeat


def _template(
    template_type: AlertTemplateType,
    label: str,
    target_type: AlertTargetType,
    condition: dict[str, Any],
    severity: AlertSeverity,
    cooldown_seconds: int,
    delivery_policy: AlertDeliveryPolicy,
    *,
    is_active: bool = True,
) -> AlertRuleTemplateProjection:
    return AlertRuleTemplateProjection(
        template_type=template_type,
        label=label,
        target_type=target_type,
        condition=condition,
        severity=severity,
        channels=[AlertChannel.APP],
        cooldown_seconds=cooldown_seconds,
        delivery_policy=delivery_policy,
        is_active=is_active,
    )


_TEMPLATES = (
    _template(
        AlertTemplateType.HOLDING_NEWS_RISK,
        "보유 종목 위험 증가",
        AlertTargetType.PORTFOLIO,
        {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
        AlertSeverity.HIGH,
        3600,
        AlertDeliveryPolicy.ONCE_PER_TRANSITION,
    ),
    _template(
        AlertTemplateType.WATCHLIST_AI_JUDGMENT,
        "관심 종목 AI 판단 변경",
        AlertTargetType.WATCHLIST,
        {"metric": "AI_JUDGMENT_CHANGED", "operator": "CHANGED", "value": None},
        AlertSeverity.MEDIUM,
        3600,
        AlertDeliveryPolicy.ONCE_PER_TRANSITION,
    ),
    _template(
        AlertTemplateType.EARNINGS_D3,
        "실적 발표 3일 전",
        AlertTargetType.WATCHLIST,
        {"metric": "EARNINGS_DATE", "operator": "LTE", "value": 3},
        AlertSeverity.MEDIUM,
        86400,
        AlertDeliveryPolicy.ONCE_PER_DAY,
    ),
    _template(
        AlertTemplateType.POSITION_WEIGHT_OVER,
        "단일 종목 비중 초과",
        AlertTargetType.PORTFOLIO,
        {"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.15},
        AlertSeverity.HIGH,
        86400,
        AlertDeliveryPolicy.ONCE_PER_DAY,
    ),
    _template(
        AlertTemplateType.NEWS_RISK_HIGH,
        "뉴스 위험도 High 이상",
        AlertTargetType.SYMBOL,
        {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
        AlertSeverity.HIGH,
        3600,
        AlertDeliveryPolicy.ONCE_PER_TRANSITION,
    ),
    _template(
        AlertTemplateType.TOPIC_IMPACT_SURGE,
        "토픽 영향도 급등",
        AlertTargetType.TOPIC,
        {"metric": "TOPIC_IMPACT_SCORE", "operator": "GTE", "value": 80},
        AlertSeverity.HIGH,
        3600,
        AlertDeliveryPolicy.ONCE_PER_DAY,
        is_active=False,
    ),
)
_TEMPLATES_BY_TYPE = {template.template_type: template for template in _TEMPLATES}

_ORDERED_OPERATORS = {
    AlertOperator.EQ,
    AlertOperator.GTE,
    AlertOperator.LTE,
}
_TRANSITION_METRICS = {
    AlertMetric.SIGNAL_CHANGED,
    AlertMetric.AI_JUDGMENT_CHANGED,
}


def validate_condition(condition: dict[str, Any]) -> None:
    if set(condition) == {"all"}:
        members = condition["all"]
        if not isinstance(members, list) or not members:
            raise _condition_error()
        for member in members:
            if not isinstance(member, dict) or "all" in member:
                raise _condition_error()
            _validate_single_condition(member)
        return
    _validate_single_condition(condition)


def _validate_single_condition(condition: dict[str, Any]) -> None:
    if set(condition) != {"metric", "operator", "value"}:
        raise _condition_error()
    try:
        metric = AlertMetric(condition["metric"])
        operator = AlertOperator(condition["operator"])
    except (TypeError, ValueError) as exc:
        raise _condition_error() from exc
    value = condition["value"]

    if metric == AlertMetric.TOPIC_IMPACT_SCORE:
        raise _condition_error()
    if metric in _TRANSITION_METRICS:
        if operator != AlertOperator.CHANGED or value is not None:
            raise _condition_error()
        return
    if operator not in _ORDERED_OPERATORS:
        raise _condition_error()
    if metric == AlertMetric.NEWS_RISK and value not in {member.value for member in NewsRisk}:
        raise _condition_error()
    if metric == AlertMetric.THEME_HEAT and value not in {member.value for member in ThemeHeat}:
        raise _condition_error()
    if metric == AlertMetric.PRICE_CHANGE_1D and not _is_number(value):
        raise _condition_error()
    if metric == AlertMetric.POSITION_WEIGHT and (
        not _is_number(value) or not 0 <= float(value) <= 1
    ):
        raise _condition_error()
    if metric == AlertMetric.EARNINGS_DATE and (
        not isinstance(value, int) or isinstance(value, bool) or value < 0
    ):
        raise _condition_error()


def _is_number(value: object) -> bool:
    return (
        isinstance(value, Real)
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


def _condition_error() -> AppException:
    return AppException(
        status_code=422,
        detail="알림 규칙 조건이 올바르지 않습니다.",
        error_code=ErrorCode.VALIDATION_ERROR,
    )


class AlertRuleService:
    def __init__(self, db: Session) -> None:
        self.repo = AlertRuleRepository(db)

    def list_templates(self) -> list[AlertRuleTemplateProjection]:
        return [template.model_copy(deep=True) for template in _TEMPLATES]

    def create_rule(self, user_id: int, data: AlertRuleCreate) -> AlertRuleProjection:
        template = _TEMPLATES_BY_TYPE[data.template_type]
        if not template.is_active:
            raise AppException(
                status_code=422,
                detail="비활성 알림 규칙 템플릿입니다.",
                error_code=ErrorCode.VALIDATION_ERROR,
            )
        condition = data.condition if data.condition is not None else template.condition
        validate_condition(condition)
        values: dict[str, object] = {
            "name": data.name or template.label,
            "source": AlertRuleSource.USER.value,
            "template_type": template.template_type.value,
            "target_type": template.target_type.value,
            "target_id": data.target_id,
            "condition": condition,
            "severity": (data.severity or template.severity).value,
            "channels": [channel.value for channel in (data.channels or template.channels)],
            "enabled": data.enabled,
            "cooldown_seconds": data.cooldown_seconds
            if data.cooldown_seconds is not None
            else template.cooldown_seconds,
            "delivery_policy": (data.delivery_policy or template.delivery_policy).value,
        }
        return self._project(self.repo.create(user_id, values))

    def list_rules(
        self,
        user_id: int,
        *,
        status: str | None = None,
        target_type: AlertTargetType | None = None,
        offset: int = 0,
        limit: int | None = None,
        sort: str = "-created_at",
    ) -> list[AlertRuleProjection]:
        enabled = None if status is None else status == "ACTIVE"
        return [
            self._project(rule)
            for rule in self.repo.list_by_user(
                user_id,
                enabled=enabled,
                target_type=target_type.value if target_type is not None else None,
                offset=offset,
                limit=limit,
                sort=sort,
            )
        ]

    def count_rules(
        self,
        user_id: int,
        *,
        status: str | None = None,
        target_type: AlertTargetType | None = None,
    ) -> int:
        enabled = None if status is None else status == "ACTIVE"
        return self.repo.count_by_user(
            user_id,
            enabled=enabled,
            target_type=target_type.value if target_type is not None else None,
        )

    def update_rule(
        self,
        alert_rule_id: int,
        user_id: int,
        data: AlertRuleUpdate,
    ) -> AlertRuleProjection:
        alert_rule = self._get_owned_rule(alert_rule_id, user_id)
        if data.condition is not None:
            validate_condition(data.condition)
        if data.target_type in {AlertTargetType.TOPIC, AlertTargetType.MARKET}:
            raise AppException(
                status_code=422,
                detail="비활성 알림 대상 유형입니다.",
                error_code=ErrorCode.VALIDATION_ERROR,
            )
        return self._project(self.repo.update(alert_rule, data))

    def pause_rule(self, alert_rule_id: int, user_id: int) -> AlertRuleProjection:
        alert_rule = self._get_owned_rule(alert_rule_id, user_id)
        return self._project(self.repo.set_enabled(alert_rule, enabled=False))

    def resume_rule(self, alert_rule_id: int, user_id: int) -> AlertRuleProjection:
        alert_rule = self._get_owned_rule(alert_rule_id, user_id)
        return self._project(self.repo.set_enabled(alert_rule, enabled=True))

    def delete_rule(self, alert_rule_id: int, user_id: int) -> None:
        alert_rule = self._get_owned_rule(alert_rule_id, user_id)
        if alert_rule.source == AlertRuleSource.SYSTEM.value:
            raise AppException(
                status_code=403,
                detail="시스템 알림 규칙은 삭제할 수 없습니다.",
                error_code=ErrorCode.ALERT_RULE_FORBIDDEN,
            )
        self.repo.delete(alert_rule)

    def get_overview(self, user_id: int) -> AlertOverviewProjection:
        as_of = datetime.now(UTC)
        today_start = as_of.replace(hour=0, minute=0, second=0, microsecond=0)
        return AlertOverviewProjection(
            active_rule_count=self.repo.count_by_user(user_id, enabled=True),
            triggered_today_count=self.repo.count_events_triggered_since(user_id, today_start),
            high_severity_count=self.repo.count_high_severity_events(user_id),
            paused_rule_count=self.repo.count_by_user(user_id, enabled=False),
            unread_count=self.repo.count_unread_events(user_id),
            as_of=as_of,
        )

    def _get_owned_rule(self, alert_rule_id: int, user_id: int) -> AlertRule:
        alert_rule = self.repo.get_by_id(alert_rule_id)
        if alert_rule is None:
            raise AppException(
                status_code=404,
                detail="알림 규칙을 찾을 수 없습니다.",
                error_code=ErrorCode.ALERT_RULE_NOT_FOUND,
            )
        if alert_rule.user_id != user_id:
            raise AppException(
                status_code=403,
                detail="알림 규칙 접근 권한이 없습니다.",
                error_code=ErrorCode.ALERT_RULE_FORBIDDEN,
            )
        return alert_rule

    def _project(self, alert_rule: AlertRule) -> AlertRuleProjection:
        return AlertRuleProjection(
            id=alert_rule.id,
            user_id=alert_rule.user_id,
            name=alert_rule.name,
            source=alert_rule.source,
            template_type=alert_rule.template_type,
            target_type=alert_rule.target_type,
            target_id=alert_rule.target_id,
            condition=alert_rule.condition,
            severity=alert_rule.severity,
            channels=alert_rule.channels,
            enabled=alert_rule.enabled,
            status="ACTIVE" if alert_rule.enabled else "PAUSED",
            cooldown_seconds=alert_rule.cooldown_seconds,
            delivery_policy=alert_rule.delivery_policy,
            last_triggered_at=alert_rule.last_triggered_at,
            created_at=alert_rule.created_at,
            updated_at=alert_rule.updated_at,
        )
