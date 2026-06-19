from app.domains.signals.rules.base import Rule, RuleContext
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType


class HighImpactNewsRule(Rule):
    def evaluate(self, context: RuleContext) -> SignalCreate | None:
        impact_level = context.news_item.impact_level
        if impact_level not in {"HIGH", "CRITICAL"}:
            return None

        score = 80 if impact_level == "CRITICAL" else 60
        summary = context.news_item.summary or context.news_item.title

        return SignalCreate(
            asset_id=context.asset_id,
            news_item_id=context.news_item.id,
            signal_type=SignalType.RISK_ALERT,
            score=score,
            risk_level=impact_level,
            reason=f"High-impact news requires review: {summary}",
            evidence={
                "news_item_id": context.news_item.id,
                "impact_level": impact_level,
                "sentiment": context.news_item.sentiment,
            },
        )
