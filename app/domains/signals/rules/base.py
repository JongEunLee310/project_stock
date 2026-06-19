from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.domains.news.model import NewsItem
from app.domains.signals.schema import SignalCreate
from app.domains.theses.conflict_schema import ThesisConflictResult
from app.domains.theses.model import InvestmentThesis


@dataclass
class RuleContext:
    asset_id: int
    news_item: NewsItem
    thesis: InvestmentThesis | None = None
    conflict_result: ThesisConflictResult | None = None


class Rule(ABC):
    @abstractmethod
    def evaluate(self, context: RuleContext) -> SignalCreate | None:
        pass
