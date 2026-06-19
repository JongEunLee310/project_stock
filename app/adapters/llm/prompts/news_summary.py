import json

from app.adapters.llm.base import LLMMessage
from app.domains.news.schema import NewsSummaryResult


def build_news_summary_messages(title: str, body: str) -> list[LLMMessage]:
    schema_json = json.dumps(NewsSummaryResult.model_json_schema(), ensure_ascii=False)
    return [
        LLMMessage(
            role="system",
            content=(
                "You are a stock news analyst. Summarize the news as a JSON object "
                "that strictly matches this JSON Schema. Return only JSON. "
                f"JSON Schema: {schema_json}"
            ),
        ),
        LLMMessage(
            role="user",
            content=f"Title:\n{title}\n\nBody:\n{body}",
        ),
    ]
