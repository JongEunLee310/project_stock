from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.decision_logs.model import DecisionLog, DecisionReviewTrigger
from app.domains.decision_logs.review_trigger_service import (
    DecisionReviewTriggerService,
    ReviewTriggerCycleSummary,
)
from app.domains.decision_logs.schema import DecisionReviewTriggerInput
from app.domains.jobs.model import JobRun
from app.domains.prices.model import StockPriceBar
from app.domains.signals.model import Signal
from app.domains.users.model import User
from app.worker.jobs import decision_review_triggers as review_trigger_jobs


@pytest.mark.parametrize(
    ("trigger_type", "condition"),
    [
        ("DATE", {}),
        ("PRICE", {"op": "gte", "value": 100}),
        ("SIGNAL_CHANGE", {"to": "RISK_ALERT"}),
        ("METRIC", {"metric": "pe", "op": "lte", "value": 20.5}),
        ("EVENT", {"event_type": "earnings"}),
    ],
)
def test_review_trigger_condition_schemas_accept_contract_shapes(
    trigger_type: str,
    condition: dict[str, object],
) -> None:
    parsed = DecisionReviewTriggerInput.model_validate(
        {"type": trigger_type, "condition": condition}
    )

    assert parsed.condition == condition


@pytest.mark.parametrize(
    ("trigger_type", "condition"),
    [
        ("PRICE", {"op": "eq", "value": 100}),
        ("PRICE", {"op": "gte", "value": "100"}),
        ("SIGNAL_CHANGE", {"to": "UNKNOWN"}),
        ("METRIC", {"metric": "pe", "op": "gte"}),
        ("EVENT", {"event": "earnings"}),
    ],
)
def test_review_trigger_condition_schemas_reject_invalid_shapes(
    trigger_type: str,
    condition: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DecisionReviewTriggerInput.model_validate(
            {"type": trigger_type, "condition": condition}
        )


def _decision(
    *,
    user_id: int,
    symbol: str,
    status: str = "ACTIVE",
) -> DecisionLog:
    return DecisionLog(
        user_id=user_id,
        target_type="SYMBOL",
        target_id=symbol,
        symbol=symbol,
        decision_type="WATCH",
        status=status,
        created_by="USER",
    )


def _trigger(
    decision_id: int,
    trigger_type: str,
    condition: dict[str, object],
) -> DecisionReviewTrigger:
    return DecisionReviewTrigger(
        decision_id=decision_id,
        trigger_type=trigger_type,
        condition=condition,
        status="PENDING",
    )


def _price(symbol: str, close: str) -> StockPriceBar:
    price = Decimal(close)
    return StockPriceBar(
        symbol=symbol,
        market="NASDAQ",
        interval="1d",
        timestamp=datetime(2026, 7, 21, tzinfo=UTC),
        open_price=price,
        high_price=price,
        low_price=price,
        close_price=price,
        adjusted_close_price=price,
        volume=1,
        currency="USD",
        source="test",
    )


def test_price_triggers_transition_only_when_condition_matches(db: Session) -> None:
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    db.add(User(id=1, email="price@example.com", hashed_password="hash"))
    matched = _decision(user_id=1, symbol="AAPL")
    unmatched = _decision(user_id=1, symbol="MSFT")
    db.add_all([matched, unmatched])
    db.flush()
    matched_trigger = _trigger(matched.id, "PRICE", {"op": "gte", "value": 200})
    unmatched_trigger = _trigger(unmatched.id, "PRICE", {"op": "lte", "value": 300})
    db.add_all(
        [
            matched_trigger,
            unmatched_trigger,
            _price("AAPL", "210"),
            _price("MSFT", "310"),
        ]
    )
    db.commit()

    summary = DecisionReviewTriggerService(db).run_cycle(now=now)

    assert summary == ReviewTriggerCycleSummary(
        evaluated_count=2,
        transitioned_count=1,
    )
    assert matched_trigger.status == "TRIGGERED"
    assert matched_trigger.triggered_at is not None
    assert matched_trigger.triggered_at.replace(tzinfo=UTC) == now
    assert matched.status == "REVIEW_DUE"
    assert unmatched_trigger.status == "PENDING"
    assert unmatched_trigger.triggered_at is None
    assert unmatched.status == "ACTIVE"


def test_signal_trigger_matches_current_signal_and_skips_invalid_or_missing_data(
    db: Session,
) -> None:
    now = datetime(2026, 7, 21, 12, tzinfo=UTC)
    db.add(User(id=1, email="signal@example.com", hashed_password="hash"))
    asset = Asset(symbol="AAPL", market="NASDAQ", name="Apple")
    db.add(asset)
    db.flush()
    db.add(
        Signal(
            asset_id=asset.id,
            signal_type="RISK_ALERT",
            score=90,
            reason="risk",
        )
    )
    matched = _decision(user_id=1, symbol="AAPL")
    missing = _decision(user_id=1, symbol="MSFT")
    invalid = _decision(user_id=1, symbol="NVDA")
    inactive = _decision(user_id=1, symbol="TSLA", status="REVIEWED")
    metric_only = _decision(user_id=1, symbol="META")
    db.add_all([matched, missing, invalid, inactive, metric_only])
    db.flush()
    matched_trigger = _trigger(
        matched.id,
        "SIGNAL_CHANGE",
        {"to": "RISK_ALERT"},
    )
    missing_trigger = _trigger(
        missing.id,
        "SIGNAL_CHANGE",
        {"to": "WATCH"},
    )
    invalid_trigger = _trigger(invalid.id, "PRICE", {"op": "gte", "value": "bad"})
    inactive_trigger = _trigger(inactive.id, "PRICE", {"op": "gte", "value": 1})
    metric_trigger = _trigger(
        metric_only.id,
        "METRIC",
        {"metric": "pe", "op": "gte", "value": 30},
    )
    event_trigger = _trigger(
        metric_only.id,
        "EVENT",
        {"event_type": "earnings"},
    )
    db.add_all(
        [
            matched_trigger,
            missing_trigger,
            invalid_trigger,
            inactive_trigger,
            metric_trigger,
            event_trigger,
            _price("TSLA", "250"),
        ]
    )
    db.commit()

    summary = DecisionReviewTriggerService(db).run_cycle(now=now)

    assert summary == ReviewTriggerCycleSummary(
        evaluated_count=3,
        transitioned_count=1,
    )
    assert matched_trigger.status == "TRIGGERED"
    assert matched.status == "REVIEW_DUE"
    for trigger in (
        missing_trigger,
        invalid_trigger,
        inactive_trigger,
        metric_trigger,
        event_trigger,
    ):
        assert trigger.status == "PENDING"
        assert trigger.triggered_at is None
    assert inactive.status == "REVIEWED"
    assert metric_only.status == "ACTIVE"


def test_review_trigger_worker_records_cycle_summary(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        def __init__(self, engine_db: Session) -> None:
            assert engine_db is db

        def run_cycle(self) -> ReviewTriggerCycleSummary:
            return ReviewTriggerCycleSummary(
                evaluated_count=4,
                transitioned_count=2,
            )

    monkeypatch.setattr(review_trigger_jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(
        review_trigger_jobs,
        "DecisionReviewTriggerService",
        FakeEngine,
    )

    review_trigger_jobs.evaluate_decision_review_triggers_job()

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "decision_review_trigger_evaluation"
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "evaluated_count": 4,
        "transitioned_count": 2,
    }
