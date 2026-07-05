from enum import Enum
from typing import Any

from pydantic import BaseModel, ValidationError

from app.adapters.llm.types import RiskLevel


class EscalationTrigger(str, Enum):
    HIGH_RISK_INPUT = "HIGH_RISK_INPUT"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    SCHEMA_VALIDATION_FAILED = "SCHEMA_VALIDATION_FAILED"


class EscalationPolicy:
    def __init__(self, confidence_threshold: float) -> None:
        self.confidence_threshold = confidence_threshold

    def evaluate_pre_call(
        self,
        risk_level: RiskLevel,
    ) -> EscalationTrigger | None:
        if risk_level == RiskLevel.HIGH:
            return EscalationTrigger.HIGH_RISK_INPUT
        return None

    def evaluate_post_call(
        self,
        output: dict[str, Any],
        schema: type[BaseModel],
    ) -> EscalationTrigger | None:
        try:
            validated_output = schema.model_validate(output)
        except ValidationError:
            return EscalationTrigger.SCHEMA_VALIDATION_FAILED

        confidence = getattr(validated_output, "confidence", output.get("confidence"))
        if (
            isinstance(confidence, int | float)
            and confidence < self.confidence_threshold
        ):
            return EscalationTrigger.LOW_CONFIDENCE
        return None
