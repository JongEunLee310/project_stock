from datetime import date
from typing import Any

from pydantic import BaseModel

from app.domains.agents.thesis_watch.types import ThesisVerdict


class ThesisCheckCreate(BaseModel):
    user_id: int
    decision_id: int
    asset_id: int
    check_date: date
    verdict: ThesisVerdict
    max_severity: str | None = None
    content: dict[str, Any]
