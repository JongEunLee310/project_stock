import json

from app.adapters.llm.base import LLMMessage
from app.domains.theses.conflict_schema import ThesisConflictResult


def build_thesis_conflict_messages(
    thesis_summary: str,
    invalidation_conditions: str,
    news_summary: str,
    news_positive_factors: list[str],
    news_negative_factors: list[str],
) -> list[LLMMessage]:
    schema_json = json.dumps(ThesisConflictResult.model_json_schema(), ensure_ascii=False)
    return [
        LLMMessage(
            role="system",
            content=(
                "You are an investment thesis conflict analyst. Determine whether "
                "the news supports, is neutral to, or conflicts with the thesis. "
                "Return only JSON that strictly matches this JSON Schema. "
                f"JSON Schema: {schema_json}"
            ),
        ),
        LLMMessage(
            role="user",
            content=(
                f"Investment thesis:\n{thesis_summary}\n\n"
                f"Invalidation conditions:\n{invalidation_conditions}\n\n"
                f"News summary:\n{news_summary}\n\n"
                "News positive factors:\n"
                f"{json.dumps(news_positive_factors, ensure_ascii=False)}\n\n"
                "News negative factors:\n"
                f"{json.dumps(news_negative_factors, ensure_ascii=False)}"
            ),
        ),
    ]
