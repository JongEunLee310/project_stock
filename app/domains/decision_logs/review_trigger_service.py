from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.domains.assets.repository import AssetRepository
from app.domains.decision_logs.model import DecisionLog, DecisionReviewTrigger
from app.domains.decision_logs.repository import DecisionLogRepository
from app.domains.decision_logs.schema import (
    PriceReviewTriggerCondition,
    SignalChangeReviewTriggerCondition,
)
from app.domains.decision_logs.types import ReviewTriggerType
from app.domains.prices.repository import PriceBarRepository
from app.domains.signals.service import SignalService


@dataclass(frozen=True)
class ReviewTriggerCycleSummary:
    evaluated_count: int = 0
    transitioned_count: int = 0

    def as_metadata(self) -> dict[str, int]:
        return {
            "evaluated_count": self.evaluated_count,
            "transitioned_count": self.transitioned_count,
        }


class DecisionReviewTriggerService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DecisionLogRepository(db)
        self.price_repo = PriceBarRepository(db)
        self.asset_repo = AssetRepository(db)
        self.signal_service = SignalService(db)

    def run_cycle(self, *, now: datetime | None = None) -> ReviewTriggerCycleSummary:
        evaluated_at = now or datetime.now(UTC)
        triggers = self.repo.list_pending_event_triggers()
        transitioned_count = 0
        for decision_log, trigger in triggers:
            if not self._is_condition_met(decision_log, trigger):
                continue
            if self.repo.mark_triggered(decision_log, trigger, evaluated_at):
                transitioned_count += 1
        self.db.commit()
        return ReviewTriggerCycleSummary(
            evaluated_count=len(triggers),
            transitioned_count=transitioned_count,
        )

    def _is_condition_met(
        self,
        decision_log: DecisionLog,
        trigger: DecisionReviewTrigger,
    ) -> bool:
        try:
            if trigger.trigger_type == ReviewTriggerType.PRICE.value:
                return self._matches_price(decision_log, trigger)
            if trigger.trigger_type == ReviewTriggerType.SIGNAL_CHANGE.value:
                return self._matches_signal(decision_log, trigger)
        except (ValidationError, ValueError):
            return False
        return False

    def _matches_price(
        self,
        decision_log: DecisionLog,
        trigger: DecisionReviewTrigger,
    ) -> bool:
        condition = PriceReviewTriggerCondition.model_validate(trigger.condition)
        if decision_log.symbol is None:
            return False
        latest_price = self.price_repo.get_latest_by_symbol(decision_log.symbol)
        if latest_price is None:
            return False
        target = Decimal(str(condition.value))
        if condition.op == "gte":
            return latest_price.close_price >= target
        return latest_price.close_price <= target

    def _matches_signal(
        self,
        decision_log: DecisionLog,
        trigger: DecisionReviewTrigger,
    ) -> bool:
        condition = SignalChangeReviewTriggerCondition.model_validate(
            trigger.condition
        )
        if decision_log.symbol is None:
            return False
        assets = self.asset_repo.list_all(symbol=decision_log.symbol)
        for asset in assets:
            current_signals = self.signal_service.list_current_signals(
                asset.id,
                limit=1,
            )
            if current_signals and current_signals[0].signal_type == condition.to.value:
                return True
        return False
