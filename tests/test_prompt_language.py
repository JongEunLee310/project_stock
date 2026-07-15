import pytest

from app.adapters.llm.prompts.analysis import build_analysis_system_prompt
from app.adapters.llm.prompts.dashboard_briefing import DASHBOARD_BRIEFING_SYSTEM_PROMPT
from app.adapters.llm.prompts.language import KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
from app.adapters.llm.prompts.news_summary import build_news_summary_system_prompt
from app.adapters.llm.prompts.portfolio_briefing import PORTFOLIO_BRIEFING_SYSTEM_PROMPT
from app.adapters.llm.prompts.research_summary import RESEARCH_SUMMARY_SYSTEM_PROMPT
from app.adapters.llm.prompts.stock_recommendation import (
    STOCK_RECOMMENDATION_SYSTEM_PROMPT,
)
from app.adapters.llm.prompts.thesis_conflict import (
    build_thesis_conflict_system_prompt,
)
from app.adapters.llm.prompts.watchlist_observation import (
    WATCHLIST_OBSERVATION_SYSTEM_PROMPT,
)
from app.adapters.llm.prompts.watchlist_evaluation import (
    WATCHLIST_EVALUATION_SYSTEM_PROMPT,
)


@pytest.mark.parametrize(
    "prompt",
    [
        STOCK_RECOMMENDATION_SYSTEM_PROMPT,
        RESEARCH_SUMMARY_SYSTEM_PROMPT,
        WATCHLIST_OBSERVATION_SYSTEM_PROMPT,
        WATCHLIST_EVALUATION_SYSTEM_PROMPT,
        DASHBOARD_BRIEFING_SYSTEM_PROMPT,
        PORTFOLIO_BRIEFING_SYSTEM_PROMPT,
        build_analysis_system_prompt(),
        build_news_summary_system_prompt(),
        build_thesis_conflict_system_prompt(),
    ],
)
def test_prompts_include_korean_natural_language_instruction(prompt: str) -> None:
    assert KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION in prompt
