from app.domains.signals.model import Signal
from app.domains.signals.repository import SignalRepository
from app.domains.signals.rules.base import Rule, RuleContext
from app.domains.signals.rules.high_impact_rule import HighImpactNewsRule
from app.domains.signals.rules.thesis_conflict_rule import ThesisConflictRule


class RuleEngine:
    def __init__(self, rules: list[Rule], signal_repo: SignalRepository) -> None:
        self.rules = rules
        self.signal_repo = signal_repo

    def run(self, context: RuleContext) -> list[Signal]:
        created: list[Signal] = []
        candidates = [
            candidate
            for rule in self.rules
            if (candidate := rule.evaluate(context)) is not None
        ]

        for candidate in candidates:
            if self.signal_repo.exists_active(
                candidate.asset_id,
                candidate.signal_type.value,
                candidate.news_item_id,
            ):
                continue
            created.append(self.signal_repo.create(candidate))

        return created


def default_rules() -> list[Rule]:
    return [ThesisConflictRule(), HighImpactNewsRule()]
