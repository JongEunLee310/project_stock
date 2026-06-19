from app.domains.signals.rules.base import Rule, RuleContext
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType


class ThesisConflictRule(Rule):
    def evaluate(self, context: RuleContext) -> SignalCreate | None:
        conflict_result = context.conflict_result
        if conflict_result is None:
            return None

        if conflict_result.invalidation_triggered:
            signal_type = SignalType.THESIS_BROKEN
            risk_level = "CRITICAL"
            score = 90
        elif conflict_result.status == "CONFLICTS":
            signal_type = SignalType.RISK_ALERT
            risk_level = "HIGH"
            score = 70
        else:
            return None

        return SignalCreate(
            asset_id=context.asset_id,
            thesis_id=context.thesis.id if context.thesis is not None else None,
            news_item_id=context.news_item.id,
            signal_type=signal_type,
            score=score,
            risk_level=risk_level,
            reason=conflict_result.reason,
            evidence={
                "status": conflict_result.status,
                "invalidation_triggered": conflict_result.invalidation_triggered,
                "news_item_id": context.news_item.id,
            },
        )
