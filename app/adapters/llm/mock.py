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
        "category": "OTHER",
    },
    "ThesisConflictResult": {
        "status": "NEUTRAL",
        "reason": "Mock conflict analysis is neutral.",
        "invalidation_triggered": False,
    },
    "DecisionAssistResult": {
        "structured_thesis": "Mock structured thesis.",
        "structured_rationale": "Mock structured rationale.",
        "counter_arguments": ["Mock counter argument."],
        "risk_candidates": [
            {"type": "VALUATION", "reason": "Mock risk candidate."}
        ],
        "bias_candidates": [{"type": "FOMO", "reason": "Mock bias candidate."}],
        "vague_flags": [
            {"quote": "Mock vague phrase", "suggestion": "Add a measurable basis."}
        ],
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
    # Enum values are sourced from app/domains/watchlists/types.py.
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
    "ResearchSummaryResult": {
        "stance": "WATCH",
        "stance_confidence": "0.70",
        "stance_comment": "현재 데이터 흐름을 확인하며 후속 지표를 점검할 단계입니다.",
        "headline": "핵심 지표와 최근 뉴스 흐름을 함께 점검해야 합니다.",
        "body": "가격 흐름과 최근 공개 정보를 바탕으로 기회와 위험 요인을 균형 있게 확인해야 합니다.",
        "positive_factors": ["최근 데이터에서 긍정적인 흐름이 관찰됩니다."],
        "caution_factors": ["추가 데이터로 흐름의 지속성을 확인해야 합니다."],
        "next_checks": ["다음 실적과 주요 지표 변화를 확인하세요."],
        "counter_points": [
            {
                "id": "limited_evidence",
                "claim": "현재 근거만으로 방향성을 확정하기 어렵습니다.",
                "basis": "공개 데이터의 범위와 최신성에 제한이 있을 수 있습니다.",
                "basis_type": "FUNDAMENTALS",
                "strength": "MODERATE",
                "source_label": "AI 분석",
            }
        ],
        "confidence_basis": "가격·뉴스·시그널 데이터의 범위와 최신성을 함께 반영했습니다.",
        "key_risks": [
            {
                "id": "data_limit",
                "title": "데이터 제한",
                "level": "MEDIUM",
                "description": "새로운 정보가 판단을 바꿀 가능성을 점검하세요.",
                "evidence": ["최근 공시와 실적 자료의 갱신 여부를 확인하세요."],
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
