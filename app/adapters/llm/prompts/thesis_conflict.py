import json

from app.domains.theses.conflict_schema import ThesisConflictResult


def build_thesis_conflict_system_prompt() -> str:
    schema_json = json.dumps(ThesisConflictResult.model_json_schema(), ensure_ascii=False)
    return (
        "You are an investment thesis conflict analyst. Determine whether "
        "the news supports, is neutral to, or conflicts with the thesis. "
        "Return only JSON that strictly matches this JSON Schema. "
        f"JSON Schema: {schema_json}"
    )
