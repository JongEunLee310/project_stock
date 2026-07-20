from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Protocol

from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertMetric

MetricValue = str | int | float | bool | None


class MetricUnavailableReason(str, Enum):
    NO_TARGET = "NO_TARGET"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class MetricSnapshot:
    values: dict[AlertMetric, MetricValue] = field(default_factory=dict)
    previous_values: dict[AlertMetric, MetricValue] = field(default_factory=dict)
    evidence: dict[AlertMetric, list[dict[str, Any]]] = field(default_factory=dict)
    unsupported_metrics: frozenset[AlertMetric] = frozenset()
    asset_id: int | None = None
    unavailable_reasons: dict[AlertMetric, MetricUnavailableReason] = field(
        default_factory=dict
    )


@dataclass(frozen=True)
class AlertEvaluationResult:
    matched: bool
    triggered_value: dict[str, Any]
    evidence: list[dict[str, Any]]
    event_fingerprint: str
    is_transition: bool
    unsupported_metrics: tuple[str, ...] = ()
    unavailable_metrics: tuple[str, ...] = ()
    unavailable_reasons: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class AlertCycleSummary:
    evaluated_count: int = 0
    matched_count: int = 0
    emitted_count: int = 0
    deduplicated_count: int = 0
    unsupported_count: int = 0
    unavailable_count: int = 0

    def as_metadata(self) -> dict[str, int]:
        return {
            "evaluated_count": self.evaluated_count,
            "matched_count": self.matched_count,
            "emitted_count": self.emitted_count,
            "deduplicated_count": self.deduplicated_count,
            "unsupported_count": self.unsupported_count,
            "unavailable_count": self.unavailable_count,
        }


class SnapshotProvider(Protocol):
    def get_snapshots(
        self,
        rule: AlertRule,
        *,
        as_of: datetime,
    ) -> list[MetricSnapshot]: ...
