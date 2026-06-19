import json
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.llm.base import LLMMessage
from app.adapters.llm.mock import MockLLMClient
from app.adapters.llm.prompts.thesis_conflict import build_thesis_conflict_messages
from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.theses.conflict_model import ThesisConflictAnalysis
from app.domains.theses.conflict_service import ThesisAnalysisService
from app.domains.theses.model import InvestmentThesis
from app.domains.users.model import User


class RecordingLLMClient(MockLLMClient):
    def __init__(self, responses: dict[str, Any]) -> None:
        super().__init__(responses)
        self.messages: list[LLMMessage] = []

    def complete_json(
        self,
        messages: list[LLMMessage],
        schema: type[BaseModel],
        timeout: float | None = None,
    ) -> dict[str, Any]:
        self.messages = messages
        return super().complete_json(messages, schema, timeout)


def create_user(db: Session) -> User:
    user = User(email="owner@example.com", hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_asset(db: Session) -> Asset:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_thesis(db: Session, asset_id: int, user_id: int) -> InvestmentThesis:
    thesis = InvestmentThesis(
        user_id=user_id,
        asset_id=asset_id,
        summary="Apple can compound earnings through services growth.",
        invalidation_conditions="Services revenue growth falls below 5%.",
    )
    db.add(thesis)
    db.commit()
    db.refresh(thesis)
    return thesis


def create_news_item(db: Session, asset_id: int, summary: str | None) -> NewsItem:
    item = NewsItem(
        asset_id=asset_id,
        title="Apple services revenue accelerates",
        url="https://example.com/apple-services",
        source="Example News",
        summary=summary,
        positive_factors=json.dumps(["Services growth accelerated"]),
        negative_factors=json.dumps(["Hardware demand remains soft"]),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_thesis_analysis_service_analyze_conflict_saves_result(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db)
    thesis = create_thesis(db, asset.id, user.id)
    item = create_news_item(db, asset.id, "Services revenue grew faster than expected.")
    client = RecordingLLMClient(
        {
            "ThesisConflictResult": {
                "status": "SUPPORTS",
                "reason": "The news reinforces the services growth thesis.",
                "invalidation_triggered": False,
            }
        }
    )

    result = ThesisAnalysisService(db, client).analyze_conflict(item.id, thesis.id)

    assert result.status == "SUPPORTS"
    assert result.invalidation_triggered is False
    assert "Apple can compound earnings" in client.messages[1].content
    assert "Services growth accelerated" in client.messages[1].content
    saved = db.scalars(select(ThesisConflictAnalysis)).all()
    assert len(saved) == 1
    assert saved[0].news_item_id == item.id
    assert saved[0].thesis_id == thesis.id
    assert saved[0].status == "SUPPORTS"


def test_thesis_analysis_service_raises_when_news_summary_missing(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db)
    thesis = create_thesis(db, asset.id, user.id)
    item = create_news_item(db, asset.id, None)

    with pytest.raises(ValueError, match="뉴스 요약 없음"):
        ThesisAnalysisService(db, MockLLMClient()).analyze_conflict(item.id, thesis.id)


def test_thesis_analysis_service_rejects_invalid_llm_response_without_saving(
    db: Session,
) -> None:
    user = create_user(db)
    asset = create_asset(db)
    thesis = create_thesis(db, asset.id, user.id)
    item = create_news_item(db, asset.id, "Services revenue declined.")
    client = MockLLMClient(
        {
            "ThesisConflictResult": {
                "status": "UNKNOWN",
                "reason": "Invalid status.",
                "invalidation_triggered": False,
            }
        }
    )

    with pytest.raises(ValidationError):
        ThesisAnalysisService(db, client).analyze_conflict(item.id, thesis.id)

    saved = db.scalars(select(ThesisConflictAnalysis)).all()
    assert saved == []


def test_build_thesis_conflict_messages_includes_thesis_and_news_content() -> None:
    messages = build_thesis_conflict_messages(
        thesis_summary="Margins expand through services mix.",
        invalidation_conditions="Services growth turns negative.",
        news_summary="Services revenue accelerated.",
        news_positive_factors=["Higher recurring revenue"],
        news_negative_factors=["FX headwind"],
    )

    assert len(messages) == 2
    assert messages[0].role == "system"
    assert "JSON Schema" in messages[0].content
    assert messages[1].role == "user"
    assert "Margins expand through services mix." in messages[1].content
    assert "Services growth turns negative." in messages[1].content
    assert "Services revenue accelerated." in messages[1].content
    assert "Higher recurring revenue" in messages[1].content
    assert "FX headwind" in messages[1].content
