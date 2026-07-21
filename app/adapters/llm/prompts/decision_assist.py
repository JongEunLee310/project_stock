import json

from app.adapters.llm.prompts.language import KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
from app.domains.decision_logs.schema import DecisionAssistResult


PROMPT_VERSION = "v1"


def build_decision_assist_system_prompt() -> str:
    schema_json = json.dumps(
        DecisionAssistResult.model_json_schema(),
        ensure_ascii=False,
    )
    return (
        "You help a user structure and challenge an investment decision draft. "
        "Do not make or finalize the decision for the user. "
        "Treat risks and behavioral biases only as check candidates, never as "
        "confirmed diagnoses. Base every suggestion on only the user's supplied "
        "text and target context; do not invent facts. Identify vague phrases and "
        "suggest what concrete evidence, metric, or condition would clarify them. "
        "Return only JSON that strictly matches this JSON Schema. "
        f"JSON Schema: {schema_json}\n\n"
        f"{KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION}"
    )
