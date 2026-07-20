import hashlib
import json
from dataclasses import dataclass
from numbers import Real
from typing import Any, TypeGuard

from app.domains.alert_engine.types import (
    AlertEvaluationResult,
    MetricSnapshot,
    MetricValue,
)
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertMetric, AlertOperator

_ORDERED_VALUES = {
    AlertMetric.NEWS_RISK: {"LOW": 0, "MEDIUM": 1, "HIGH": 2},
    AlertMetric.THEME_HEAT: {"COLD": 0, "NEUTRAL": 1, "OVERHEATED": 2},
}


@dataclass(frozen=True)
class _ConditionEvaluation:
    matched: bool
    triggered_value: dict[str, Any]
    evidence: list[dict[str, Any]]
    is_transition: bool
    unsupported_metric: str | None = None
    unavailable_metric: str | None = None


class AlertEvaluator:
    def evaluate_rule(
        self,
        rule: AlertRule,
        snapshot: MetricSnapshot,
    ) -> AlertEvaluationResult:
        condition = rule.condition
        if set(condition) == {"all"}:
            evaluations = [
                self._evaluate_condition(member, snapshot)
                for member in condition["all"]
            ]
            triggered_value: dict[str, Any] = {
                "conditions": [item.triggered_value for item in evaluations]
            }
        else:
            evaluations = [self._evaluate_condition(condition, snapshot)]
            triggered_value = evaluations[0].triggered_value

        matched = all(item.matched for item in evaluations)
        evidence = [entry for item in evaluations for entry in item.evidence]
        unsupported = tuple(
            sorted(
                {
                    item.unsupported_metric
                    for item in evaluations
                    if item.unsupported_metric is not None
                }
            )
        )
        unavailable = tuple(
            sorted(
                {
                    item.unavailable_metric
                    for item in evaluations
                    if item.unavailable_metric is not None
                }
            )
        )
        fingerprint_payload = {
            "condition": condition,
            "triggered_value": triggered_value,
        }
        fingerprint = hashlib.sha256(
            json.dumps(
                fingerprint_payload,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode()
        ).hexdigest()
        return AlertEvaluationResult(
            matched=matched,
            triggered_value=triggered_value,
            evidence=evidence,
            event_fingerprint=fingerprint,
            is_transition=matched and any(item.is_transition for item in evaluations),
            unsupported_metrics=unsupported,
            unavailable_metrics=unavailable,
        )

    def _evaluate_condition(
        self,
        condition: dict[str, Any],
        snapshot: MetricSnapshot,
    ) -> _ConditionEvaluation:
        metric = AlertMetric(condition["metric"])
        operator = AlertOperator(condition["operator"])
        threshold = condition["value"]
        has_previous = metric in snapshot.previous_values
        previous = snapshot.previous_values.get(metric)
        current = snapshot.values.get(metric)
        triggered_value = {
            "metric": metric.value,
            "current": current,
            "previous": previous,
            "threshold": threshold,
        }
        if metric in snapshot.unsupported_metrics:
            return _ConditionEvaluation(
                matched=False,
                triggered_value=triggered_value,
                evidence=[],
                is_transition=False,
                unsupported_metric=metric.value,
            )
        if metric not in snapshot.values:
            return _ConditionEvaluation(
                matched=False,
                triggered_value=triggered_value,
                evidence=[],
                is_transition=False,
                unavailable_metric=metric.value,
            )

        matched = self._compare(
            metric,
            operator,
            current,
            threshold,
            previous=previous,
            has_previous=has_previous,
        )
        return _ConditionEvaluation(
            matched=matched,
            triggered_value=triggered_value,
            evidence=snapshot.evidence.get(metric, []),
            is_transition=has_previous and current != previous,
        )

    def _compare(
        self,
        metric: AlertMetric,
        operator: AlertOperator,
        current: MetricValue,
        threshold: object,
        *,
        previous: MetricValue,
        has_previous: bool,
    ) -> bool:
        if operator == AlertOperator.CHANGED:
            return has_previous and current != previous
        if operator == AlertOperator.EQ:
            return current == threshold

        current_ordered = self._ordered_value(metric, current)
        threshold_ordered = self._ordered_value(metric, threshold)
        if current_ordered is not None and threshold_ordered is not None:
            left: float = float(current_ordered)
            right: float = float(threshold_ordered)
        elif self._is_number(current) and self._is_number(threshold):
            left = float(current)
            right = float(threshold)
        else:
            return False
        if operator == AlertOperator.GTE:
            return left >= right
        return left <= right

    def _ordered_value(self, metric: AlertMetric, value: object) -> int | None:
        if not isinstance(value, str):
            return None
        return _ORDERED_VALUES.get(metric, {}).get(value)

    def _is_number(self, value: object) -> TypeGuard[Real]:
        return isinstance(value, Real) and not isinstance(value, bool)
