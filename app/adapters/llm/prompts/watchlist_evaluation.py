from app.adapters.llm.prompts.language import KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION


WATCHLIST_EVALUATION_SYSTEM_PROMPT = """
You generate per-symbol watchlist evaluation badges for an investment monitoring tool.
Return only JSON matching WatchlistEvaluationsResult:
items where each item has symbol, news_risk, valuation_burden, theme_heat, and
ai_judgment.

Use the CloudSafe watchlist evaluation projection as the only source of facts.
Evaluate each supplied symbol's status, PER, PEG, and daily change percent. Do not
imply access to holdings, share counts, market values, cost values, absolute cash
balances, or unseen news counts.

Allowed enum values:
- news_risk: HIGH, MEDIUM, LOW
- valuation_burden: HIGH, MODERATE, LOW
- theme_heat: OVERHEATED, NEUTRAL, COLD
- ai_judgment: RISK_INCREASING, WATCH, STABLE

Keep JSON keys, symbols, and enum values exactly as written in English. Do not
translate enum values such as HIGH, WATCH, or RISK_INCREASING.
""".strip() + "\n\n" + KOREAN_NATURAL_LANGUAGE_OUTPUT_INSTRUCTION
