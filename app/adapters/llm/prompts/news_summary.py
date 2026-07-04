import json

from app.domains.news.schema import NewsSummaryResult


def build_news_summary_system_prompt() -> str:
    schema_json = json.dumps(NewsSummaryResult.model_json_schema(), ensure_ascii=False)
    return (
        "You are a stock news analyst. Summarize the news as a JSON object "
        "that strictly matches this JSON Schema. Return only JSON. "
        f"JSON Schema: {schema_json}"
    )
