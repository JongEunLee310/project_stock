import json

from app.domains.llm_analysis.schema import LLMAnalysisResult


ANALYSIS_PROMPT_VERSION = "v1"


def build_analysis_system_prompt() -> str:
    schema_json = json.dumps(LLMAnalysisResult.model_json_schema(), ensure_ascii=False)
    return (
        "You are an investment analysis assistant. Analyze the provided context bundle "
        "and return only a JSON object that strictly matches this JSON Schema. "
        f"JSON Schema: {schema_json}"
    )
