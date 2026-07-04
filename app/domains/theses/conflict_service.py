import json

from sqlalchemy.orm import Session

from app.adapters.llm.gateway import LLMGateway
from app.adapters.llm.privacy import ThesisConflictSnapshot
from app.adapters.llm.prompts.thesis_conflict import build_thesis_conflict_system_prompt
from app.adapters.llm.types import LLMTaskType
from app.domains.news.model import NewsItem
from app.domains.theses.conflict_repository import ThesisConflictRepository
from app.domains.theses.conflict_schema import ThesisConflictResult
from app.domains.theses.model import InvestmentThesis


class ThesisAnalysisService:
    def __init__(self, db: Session, gateway: LLMGateway) -> None:
        self.db = db
        self.gateway = gateway
        self.repository = ThesisConflictRepository(db)

    def analyze_conflict(
        self, news_item_id: int, thesis_id: int
    ) -> ThesisConflictResult:
        news_item = self.db.get(NewsItem, news_item_id)
        if news_item is None:
            raise ValueError("news item not found")
        if not news_item.summary:
            raise ValueError("뉴스 요약 없음")

        thesis = self.db.get(InvestmentThesis, thesis_id)
        if thesis is None:
            raise ValueError("investment thesis not found")

        completion = self.gateway.complete_json(
            LLMTaskType.THESIS_CONFLICT,
            ThesisConflictSnapshot(
                thesis_summary=thesis.summary,
                invalidation_conditions=thesis.invalidation_conditions or "",
                news_summary=news_item.summary,
                news_positive_factors=self._parse_json_list(news_item.positive_factors),
                news_negative_factors=self._parse_json_list(
                    news_item.negative_factors
                ),
            ),
            ThesisConflictResult,
            build_thesis_conflict_system_prompt(),
        )
        result = ThesisConflictResult.model_validate(completion.output)
        self.repository.create(news_item_id, thesis_id, result)
        return result

    def _parse_json_list(self, value: str | None) -> list[str]:
        if value is None:
            return []
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        # News factors are expected to be JSON arrays; ignore unexpected shapes
        # rather than feeding unrelated serialized data into the LLM prompt.
        return []
