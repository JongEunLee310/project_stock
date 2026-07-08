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
    "ObservationsResult": {
        "summary": "Mock watchlist observation summary.",
        "items": [{"symbol": "AAPL", "note": "Mock watchlist observation note."}],
    },
    "WatchlistEvaluationsResult": {
        "items": [
            {
                "symbol": "AAPL",
                "news_risk": "LOW",
                "valuation_burden": "MODERATE",
                "theme_heat": "NEUTRAL",
                "ai_judgment": "WATCH",
            }
        ],
    },
    "StockRecommendationResult": {
        "recommendations": [
            {
                "symbol": "AAPL",
                "rationale": "Mock recommendation rationale.",
                "reference_metrics": ["Mock metric A", "Mock metric B"],
            }
        ],
    },
    "LLMAnalysisResult": {
        "summary": "Mock LLM analysis summary.",
        "risk_level": "LOW",
        "suggested_action": "hold",
        "reasons": ["Mock analysis reason"],
        "watch_points": ["Mock watch point"],
        "counter_arguments": ["Mock counter argument"],
        "data_limitations": ["Mock data limitation"],
        "confidence": 0.7,
    },
}


class MockLLMClient(LLMClient):
    def __init__(self, responses: dict[str, Any] | None = None) -> None:
        self.responses = responses or {}

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def model_name(self) -> str:
        return "mock"

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
