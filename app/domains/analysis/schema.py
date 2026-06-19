from typing import Any

from pydantic import BaseModel


class AnalysisFlowResult(BaseModel):
    watchlist_id: int
    processed_assets: int
    created_news_items: int
    created_reports: int
    created_signals: int
    created_alerts: int
    failures: list[dict[str, Any]]
