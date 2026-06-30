from typing import Any

from pydantic import BaseModel

from app.adapters.llm.base import LLMClient, LLMMessage


DEFAULT_MOCK_RESPONSES: dict[str, Any] = {
    "NewsSummaryResult": {
        "summary": "Mock analysis summary.",
        "positive_factors": ["Mock positive factor"],
        "negative_factors": ["Mock negative factor"],
        "impact_level": "HIGH",
        "sentiment": "NEUTRAL",
    },
    "ThesisConflictResult": {
        "status": "NEUTRAL",
        "reason": "Mock conflict analysis is neutral.",
        "invalidation_triggered": False,
    },
    "BriefingResult": {
        "headline": "Mock briefing headline.",
        "body": "Mock briefing body.",
        "risk_headline": "Mock risk checks",
        "risk_checks": ["Mock risk check"],
    },
}


class MockLLMClient(LLMClient):
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}

    def complete(
        self, messages: list[LLMMessage], timeout: float | None = None
    ) -> str:
        return "mock response"

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        response = self.responses.get(schema.__name__, self.responses.get("default", {}))
        if isinstance(response, dict):
            return response
        return {"response": response}
