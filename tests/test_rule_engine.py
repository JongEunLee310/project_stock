from datetime import datetime, timedelta, timezone
from typing import Literal

import pytest
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.news.model import NewsItem
from app.domains.signals.repository import SignalRepository
from app.domains.signals.rules import (
    HighImpactNewsRule,
    RuleContext,
    RuleEngine,
    ThesisConflictRule,
)
from app.domains.signals.schema import SignalCreate
from app.domains.signals.types import SignalType
from app.domains.theses.conflict_schema import ThesisConflictResult
from app.domains.theses.model import InvestmentThesis
from app.domains.users.model import User


def news_item(
    item_id: int = 1,
    impact_level: str | None = "LOW",
    sentiment: str | None = "NEGATIVE",
) -> NewsItem:
    return NewsItem(
        id=item_id,
        asset_id=1,
        title="Guidance cut pressures the thesis",
        url="https://example.com/guidance-cut",
        source="Example News",
        summary="Management lowered guidance.",
        sentiment=sentiment,
        impact_level=impact_level,
    )


def thesis(thesis_id: int = 1) -> InvestmentThesis:
    return InvestmentThesis(
        id=thesis_id,
        user_id=1,
        asset_id=1,
        summary="Services growth offsets hardware cyclicality.",
    )


def conflict_result(
    status: Literal["SUPPORTS", "NEUTRAL", "CONFLICTS"],
    invalidation_triggered: bool = False,
) -> ThesisConflictResult:
    return ThesisConflictResult(
        status=status,
        reason="Guidance cut conflicts with the thesis.",
        invalidation_triggered=invalidation_triggered,
    )


def create_asset(db: Session) -> Asset:
    asset = Asset(symbol="AAPL", name="Apple Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def create_user(db: Session) -> User:
    user = User(email="owner@example.com", hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def create_thesis(db: Session, asset_id: int, user_id: int) -> InvestmentThesis:
    item = InvestmentThesis(
        user_id=user_id,
        asset_id=asset_id,
        summary="Services growth offsets hardware cyclicality.",
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def create_news_item(db: Session, asset_id: int, impact_level: str = "HIGH") -> NewsItem:
    item = NewsItem(
        asset_id=asset_id,
        title="Apple lowers guidance",
        url="https://example.com/apple-guidance",
        source="Example News",
        summary="Management lowered guidance.",
        sentiment="NEGATIVE",
        impact_level=impact_level,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_thesis_conflict_rule_creates_thesis_broken_for_invalidation() -> None:
    result = ThesisConflictRule().evaluate(
        RuleContext(
            asset_id=1,
            news_item=news_item(),
            thesis=thesis(),
            conflict_result=conflict_result("SUPPORTS", invalidation_triggered=True),
        )
    )

    assert result is not None
    assert result.signal_type == SignalType.THESIS_BROKEN
    assert result.risk_level == "CRITICAL"
    assert result.score == 90
    assert result.thesis_id == 1
    assert result.news_item_id == 1
    assert result.evidence == {
        "status": "SUPPORTS",
        "invalidation_triggered": True,
        "news_item_id": 1,
    }


def test_thesis_conflict_rule_creates_risk_alert_for_conflict() -> None:
    result = ThesisConflictRule().evaluate(
        RuleContext(
            asset_id=1,
            news_item=news_item(),
            thesis=thesis(),
            conflict_result=conflict_result("CONFLICTS"),
        )
    )

    assert result is not None
    assert result.signal_type == SignalType.RISK_ALERT
    assert result.risk_level == "HIGH"
    assert result.score == 70


@pytest.mark.parametrize("status", ["SUPPORTS", "NEUTRAL"])
def test_thesis_conflict_rule_ignores_supports_and_neutral(
    status: Literal["SUPPORTS", "NEUTRAL"],
) -> None:
    result = ThesisConflictRule().evaluate(
        RuleContext(
            asset_id=1,
            news_item=news_item(),
            thesis=thesis(),
            conflict_result=conflict_result(status),
        )
    )

    assert result is None


def test_thesis_conflict_rule_ignores_missing_conflict_result() -> None:
    result = ThesisConflictRule().evaluate(RuleContext(asset_id=1, news_item=news_item()))

    assert result is None


@pytest.mark.parametrize(
    ("impact_level", "expected_score"),
    [("HIGH", 60), ("CRITICAL", 80)],
)
def test_high_impact_news_rule_creates_risk_alert(
    impact_level: str,
    expected_score: int,
) -> None:
    result = HighImpactNewsRule().evaluate(
        RuleContext(asset_id=1, news_item=news_item(impact_level=impact_level))
    )

    assert result is not None
    assert result.signal_type == SignalType.RISK_ALERT
    assert result.risk_level == impact_level
    assert result.score == expected_score
    assert result.evidence == {
        "news_item_id": 1,
        "impact_level": impact_level,
        "sentiment": "NEGATIVE",
    }


@pytest.mark.parametrize("impact_level", ["LOW", None])
def test_high_impact_news_rule_ignores_low_or_missing_impact(
    impact_level: str | None,
) -> None:
    result = HighImpactNewsRule().evaluate(
        RuleContext(asset_id=1, news_item=news_item(impact_level=impact_level))
    )

    assert result is None


def test_rule_engine_run_saves_and_returns_signal(db: Session) -> None:
    asset = create_asset(db)
    user = create_user(db)
    saved_thesis = create_thesis(db, asset.id, user.id)
    saved_news = create_news_item(db, asset.id)
    repo = SignalRepository(db)
    engine = RuleEngine([ThesisConflictRule()], repo)

    created = engine.run(
        RuleContext(
            asset_id=asset.id,
            news_item=saved_news,
            thesis=saved_thesis,
            conflict_result=conflict_result("CONFLICTS"),
        )
    )

    assert len(created) == 1
    assert created[0].id > 0
    assert created[0].asset_id == asset.id
    assert created[0].signal_type == SignalType.RISK_ALERT.value


def test_rule_engine_run_skips_active_duplicate(db: Session) -> None:
    asset = create_asset(db)
    saved_news = create_news_item(db, asset.id)
    repo = SignalRepository(db)
    engine = RuleEngine([HighImpactNewsRule()], repo)
    context = RuleContext(asset_id=asset.id, news_item=saved_news)

    first = engine.run(context)
    second = engine.run(context)

    assert len(first) == 1
    assert second == []


def test_rule_engine_run_ignores_expired_duplicate(db: Session) -> None:
    asset = create_asset(db)
    saved_news = create_news_item(db, asset.id)
    repo = SignalRepository(db)
    repo.create(
        SignalCreate(
            asset_id=asset.id,
            news_item_id=saved_news.id,
            signal_type=SignalType.RISK_ALERT,
            score=60,
            risk_level="HIGH",
            reason="Expired duplicate.",
            evidence={"news_item_id": saved_news.id},
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    engine = RuleEngine([HighImpactNewsRule()], repo)

    created = engine.run(RuleContext(asset_id=asset.id, news_item=saved_news))

    assert len(created) == 1
    assert created[0].id > 0
    assert created[0].reason == "High-impact news requires review: Management lowered guidance."
