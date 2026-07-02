from typing import Literal

from pydantic import BaseModel, Field

from app.core.schema import UtcDatetime

ChecklistItemKey = Literal[
    "valuation",
    "news_overheated",
    "portfolio_concentration",
    "earnings_disclosure",
]
class BuyChecklistItem(BaseModel):
    id: ChecklistItemKey
    label: str
    description: str | None = None
    checked: bool


class BuyChecklistNoteUpdate(BaseModel):
    memo: str | None = None
    checked_item_keys: list[ChecklistItemKey] = Field(default_factory=list)


class BuyChecklistResponse(BaseModel):
    asset_id: int
    items: list[BuyChecklistItem]
    memo: str | None
    checked_item_keys: list[ChecklistItemKey]
    is_complete: bool
    decided_at: UtcDatetime | None = None
