from app.adapters.llm.types import RiskLevel
from app.domains.llm_context.schema import LLMContextBundle


HIGH_RISK_UNREALIZED_RETURN = -0.10


def derive_risk_level(bundle: LLMContextBundle) -> RiskLevel:
    for card in bundle.symbol_cards:
        if any(signal.severity == "high" for signal in card.signals):
            return RiskLevel.HIGH
        portfolio_context = card.portfolio_context
        if (
            portfolio_context is not None
            and portfolio_context.unrealized_return is not None
            and portfolio_context.unrealized_return <= HIGH_RISK_UNREALIZED_RETURN
        ):
            return RiskLevel.HIGH
    return RiskLevel.LOW
