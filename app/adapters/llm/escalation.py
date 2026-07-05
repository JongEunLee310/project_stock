from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.llm.types import RiskLevel


@dataclass(frozen=True)
class EscalationSignal:
    risk_level: RiskLevel = RiskLevel.LOW
    loss_spike: bool = False
    news_sentiment_swing: bool = False
    event_flag: bool = False
    trade_question: bool = False


class EscalationPolicy:
    def __init__(self, confidence_threshold: float | None = None) -> None:
        self.confidence_threshold = confidence_threshold

    def should_escalate_before(
        self,
        signal: EscalationSignal,
        resolved_provider: str,
    ) -> bool:
        if resolved_provider != "local":
            return False
        return (
            signal.risk_level == RiskLevel.HIGH
            or signal.loss_spike
            or signal.news_sentiment_swing
            or signal.event_flag
            or signal.trade_question
        )

    def should_verify_after(
        self,
        output: dict[str, Any],
        schema: type[BaseModel],
        first_provider: str,
    ) -> bool:
        if first_provider == "cloud":
            return False
        if self._confidence_is_below_threshold(output):
            return True
        try:
            schema.model_validate(output)
        except ValidationError:
            return True
        return False

    def _confidence_is_below_threshold(self, output: dict[str, Any]) -> bool:
        if self.confidence_threshold is None:
            return False
        confidence = output.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, int | float):
            return False
        return confidence < self.confidence_threshold
