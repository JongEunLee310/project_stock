import json
from typing import Any

import pytest
from pydantic import BaseModel
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.adapters.llm.base import LLMMessage
from app.adapters.llm.gateway import CLOUD, LOCAL, LLMGateway
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.prompts.news_summary import build_news_summary_system_prompt
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.news.service import NewsAnalysisService
from app.domains.raw_news.model import RawNewsEvent


class RecordingLLMClient(MockLLMClient):
    def __init__(self) -> None:
        super().__init__(
            {
                "NewsSummaryResult": {
                    "summary": "Fallback text was analyzed.",
                    "positive_factors": [],
                    "negative_factors": [],
                    "impact_level": "LOW",
                    "sentiment": "NEUTRAL",
                }
            }
        )
        self.messages: list[LLMMessage] = []

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.messages = messages
        return super().complete_json(messages, schema, timeout)


def make_gateway(client: MockLLMClient) -> LLMGateway:
    return LLMGateway({CLOUD: client, LOCAL: client})


def create_asset(db: Session) -> Asset:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_news_item(db: Session) -> NewsItem:
    asset = create_asset(db)
    raw_event = RawNewsEvent(
        title="Apple supplier expands production",
        url="https://example.com/news/raw",
        body="Apple supplier capacity increased and component costs fell.",
        source="Example News",
    )
    db.add(raw_event)
    db.commit()
    db.refresh(raw_event)

    item = NewsItem(
        raw_news_event_id=raw_event.id,
        asset_id=asset.id,
        title="Apple supplier expands production",
        url="https://example.com/news/normalized",
        source="Example News",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_news_item_without_raw_event(
    db: Session, raw_news_event_id: int | None = None
) -> NewsItem:
    asset = create_asset(db)
    item = NewsItem(
        raw_news_event_id=raw_news_event_id,
        asset_id=asset.id,
        title="Apple supplier update",
        url="https://example.com/news/no-raw",
        source="Example News",
        summary="Stored summary fallback.",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_news_analysis_service_summarize_updates_news_item(db: Session) -> None:
    item = create_news_item(db)
    client = MockLLMClient(
        {
            "NewsSummaryResult": {
                "summary": "Supplier capacity increased while costs declined.",
                "positive_factors": ["Higher production capacity", "Lower costs"],
                "negative_factors": ["Execution risk"],
                "impact_level": "HIGH",
                "sentiment": "POSITIVE",
                "category": "PARTNERSHIP",
            }
        }
    )

    result = NewsAnalysisService(db, make_gateway(client)).summarize(item.id)

    updated = db.get(NewsItem, item.id)
    assert updated is not None
    assert result.summary == "Supplier capacity increased while costs declined."
    assert updated.summary == result.summary
    assert updated.sentiment == "POSITIVE"
    assert updated.impact_level == "HIGH"
    assert result.category == "PARTNERSHIP"
    assert updated.category == "PARTNERSHIP"
    assert json.loads(updated.positive_factors or "[]") == [
        "Higher production capacity",
        "Lower costs",
    ]
    assert json.loads(updated.negative_factors or "[]") == ["Execution risk"]


@pytest.mark.parametrize("raw_news_event_id", [None, 999])
def test_news_analysis_service_uses_summary_fallback_when_raw_body_is_missing(
    db: Session, raw_news_event_id: int | None
) -> None:
    item = create_news_item_without_raw_event(db, raw_news_event_id)
    client = RecordingLLMClient()

    NewsAnalysisService(db, make_gateway(client)).summarize(item.id)

    assert client.messages
    payload = json.loads(client.messages[1].content)
    assert payload["title"] == "Apple supplier update"
    assert payload["body"] == "Stored summary fallback."


def test_news_analysis_service_rejects_invalid_llm_response(
    db: Session,
) -> None:
    item = create_news_item(db)
    client = MockLLMClient(
        {
            "NewsSummaryResult": {
                "summary": "Missing required fields.",
                "positive_factors": [],
                "negative_factors": [],
                "impact_level": "UNKNOWN",
                "sentiment": "POSITIVE",
            }
        }
    )

    with pytest.raises(ValidationError):
        NewsAnalysisService(db, make_gateway(client)).summarize(item.id)

    unchanged = db.get(NewsItem, item.id)
    assert unchanged is not None
    assert unchanged.summary is None
    assert unchanged.sentiment is None
    assert unchanged.impact_level is None
    assert unchanged.positive_factors is None
    assert unchanged.negative_factors is None


@pytest.mark.parametrize("category", ["UNKNOWN", 123, {"value": "PRODUCT"}])
def test_news_analysis_service_falls_back_to_none_for_invalid_category(
    db: Session,
    category: Any,
) -> None:
    item = create_news_item(db)
    client = MockLLMClient(
        {
            "NewsSummaryResult": {
                "summary": "Category could not be parsed.",
                "positive_factors": [],
                "negative_factors": [],
                "impact_level": "LOW",
                "sentiment": "NEUTRAL",
                "category": category,
            }
        }
    )

    result = NewsAnalysisService(db, make_gateway(client)).summarize(item.id)

    updated = db.get(NewsItem, item.id)
    assert updated is not None
    assert result.category is None
    assert updated.category is None


def test_news_analysis_service_raises_for_missing_news_item(db: Session) -> None:
    client = MockLLMClient()

    with pytest.raises(ValueError, match="news item not found"):
        NewsAnalysisService(db, make_gateway(client)).summarize(999)


def test_build_news_summary_system_prompt_includes_schema() -> None:
    prompt = build_news_summary_system_prompt()

    assert "You are a stock news analyst." in prompt
    assert "JSON Schema" in prompt
    assert "positive_factors" in prompt
    assert "negative_factors" in prompt
    assert "EARNINGS" in prompt
    assert "OTHER" in prompt
