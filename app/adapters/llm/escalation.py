from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.llm.types import RiskLevel


CLOUD = "cloud"
LOCAL = "local"


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
        if resolved_provider != LOCAL:
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
        if first_provider == CLOUD:
            return False
        confidence = output.get("confidence")
        if (
            self.confidence_threshold is not None
            and not isinstance(confidence, bool)
            and isinstance(confidence, int | float)
            and confidence < self.confidence_threshold
        ):
            return True
        try:
            schema.model_validate(output)
        except ValidationError:
            return True
        return False
