from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.alert_engine.dedup import AlertDedupService
from app.domains.alert_engine.evaluator import AlertEvaluator
from app.domains.alert_engine.service import AlertEngineService
from app.domains.alert_engine.snapshot_provider import (
    UNSUPPORTED_METRICS,
    MetricSnapshotProvider,
    _aggregate_derived_metric,
    _derive_signal_metrics,
)
from app.domains.alert_engine.types import AlertCycleSummary, MetricSnapshot
from app.domains.alert_events.model import AlertDelivery, AlertEvent
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import AlertMetric
from app.domains.assets.model import Asset
from app.domains.earnings.model import EarningsEvent
from app.domains.jobs.model import JobRun
from app.domains.portfolios.model import Portfolio, Position
from app.domains.prices.model import StockPriceBar
from app.domains.signals.model import Signal
from app.domains.signals.snapshot_model import AssetSignalSnapshot
from app.domains.signals.types import SignalType
from app.domains.users.model import User
from app.domains.watchlists.model import Watchlist, WatchlistItem
from app.worker.jobs import alerts as alert_jobs


def _rule(
    *,
    condition: dict[str, object],
    delivery_policy: str = "ONCE_PER_TRANSITION",
    cooldown_seconds: int = 0,
    enabled: bool = True,
) -> AlertRule:
    return AlertRule(
        id=1,
        user_id=1,
        name="Engine rule",
        source="USER",
        template_type=None,
        target_type="SYMBOL",
        target_id="AAPL",
        condition=condition,
        severity="HIGH",
        channels=["APP"],
        enabled=enabled,
        cooldown_seconds=cooldown_seconds,
        delivery_policy=delivery_policy,
    )


def test_evaluator_handles_single_and_all_conditions() -> None:
    evaluator = AlertEvaluator()
    single_rule = _rule(
        condition={"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": 3.0}
    )
    all_rule = _rule(
        condition={
            "all": [
                {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
                {"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.15},
            ]
        }
    )

    matching = evaluator.evaluate_rule(
        single_rule,
        MetricSnapshot(values={AlertMetric.PRICE_CHANGE_1D: 4.25}),
    )
    missing_member = evaluator.evaluate_rule(
        all_rule,
        MetricSnapshot(
            values={
                AlertMetric.NEWS_RISK: "HIGH",
                AlertMetric.POSITION_WEIGHT: 0.12,
            }
        ),
    )

    assert matching.matched is True
    assert matching.triggered_value == {
        "metric": "PRICE_CHANGE_1D",
        "current": 4.25,
        "previous": None,
        "threshold": 3.0,
    }
    assert missing_member.matched is False


def test_evaluator_changed_requires_an_actual_previous_state_change() -> None:
    evaluator = AlertEvaluator()
    rule = _rule(
        condition={"metric": "SIGNAL_CHANGED", "operator": "CHANGED", "value": None}
    )

    changed = evaluator.evaluate_rule(
        rule,
        MetricSnapshot(
            values={AlertMetric.SIGNAL_CHANGED: "RISK_ALERT"},
            previous_values={AlertMetric.SIGNAL_CHANGED: "WATCH"},
        ),
    )
    maintained = evaluator.evaluate_rule(
        rule,
        MetricSnapshot(
            values={AlertMetric.SIGNAL_CHANGED: "RISK_ALERT"},
            previous_values={AlertMetric.SIGNAL_CHANGED: "RISK_ALERT"},
        ),
    )
    no_history = evaluator.evaluate_rule(
        rule,
        MetricSnapshot(values={AlertMetric.SIGNAL_CHANGED: "RISK_ALERT"}),
    )

    assert changed.matched is True
    assert changed.is_transition is True
    assert maintained.matched is False
    assert maintained.is_transition is False
    assert no_history.matched is False


def test_dedup_rejects_existing_key_and_cooldown(db: Session) -> None:
    now = datetime(2026, 7, 16, 3, 0, tzinfo=UTC)
    rule = _rule(
        condition={"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": 3.0},
        cooldown_seconds=3600,
    )
    rule.last_triggered_at = now - timedelta(minutes=30)
    db.add(User(id=1, email="engine@example.com", hashed_password="hash"))
    db.add(rule)
    db.commit()
    result = AlertEvaluator().evaluate_rule(
        rule,
        MetricSnapshot(
            values={AlertMetric.PRICE_CHANGE_1D: 4.0},
            previous_values={AlertMetric.PRICE_CHANGE_1D: 2.0},
        ),
    )
    dedup = AlertDedupService(db)

    assert dedup.should_emit(rule, result, now=now) is False

    rule.last_triggered_at = None
    dedup_key = dedup.build_dedup_key(rule, result, now=now)
    db.add(
        AlertEvent(
            rule_id=rule.id,
            user_id=rule.user_id,
            target_type=rule.target_type,
            target_id=rule.target_id,
            title="existing",
            message="existing",
            severity=rule.severity,
            triggered_value=result.triggered_value,
            evidence=[],
            dedup_key=dedup_key,
            triggered_at=now - timedelta(hours=2),
        )
    )
    db.commit()

    assert dedup.should_emit(rule, result, now=now) is False


def test_dedup_once_per_transition_emits_change_not_maintained(db: Session) -> None:
    now = datetime(2026, 7, 16, 3, 0, tzinfo=UTC)
    rule = _rule(
        condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"}
    )
    db.add(User(id=1, email="transition@example.com", hashed_password="hash"))
    db.add(rule)
    db.commit()
    evaluator = AlertEvaluator()
    changed = evaluator.evaluate_rule(
        rule,
        MetricSnapshot(
            values={AlertMetric.NEWS_RISK: "HIGH"},
            previous_values={AlertMetric.NEWS_RISK: "MEDIUM"},
        ),
    )
    maintained = evaluator.evaluate_rule(
        rule,
        MetricSnapshot(
            values={AlertMetric.NEWS_RISK: "HIGH"},
            previous_values={AlertMetric.NEWS_RISK: "HIGH"},
        ),
    )
    dedup = AlertDedupService(db)

    assert dedup.should_emit(rule, changed, now=now) is True
    assert dedup.should_emit(rule, maintained, now=now) is False


def test_dedup_once_per_day_uses_utc_day_bucket(db: Session) -> None:
    now = datetime(2026, 7, 16, 23, 55, tzinfo=UTC)
    rule = _rule(
        condition={"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.15},
        delivery_policy="ONCE_PER_DAY",
    )
    db.add(User(id=1, email="daily@example.com", hashed_password="hash"))
    db.add(rule)
    db.commit()
    result = AlertEvaluator().evaluate_rule(
        rule,
        MetricSnapshot(values={AlertMetric.POSITION_WEIGHT: 0.2}),
    )
    dedup = AlertDedupService(db)
    db.add(
        AlertEvent(
            rule_id=rule.id,
            user_id=rule.user_id,
            target_type=rule.target_type,
            target_id=rule.target_id,
            title="today",
            message="today",
            severity=rule.severity,
            triggered_value=result.triggered_value,
            evidence=[],
            dedup_key=dedup.build_dedup_key(rule, result, now=now),
            triggered_at=now,
        )
    )
    db.commit()

    assert dedup.should_emit(rule, result, now=now) is False
    assert dedup.should_emit(rule, result, now=now + timedelta(minutes=10)) is True


class _SnapshotProvider:
    def get_snapshot(
        self,
        rule: AlertRule,
        *,
        as_of: datetime,
    ) -> MetricSnapshot:
        return MetricSnapshot(
            values={AlertMetric.PRICE_CHANGE_1D: 4.0},
            previous_values={AlertMetric.PRICE_CHANGE_1D: 2.0},
            evidence={
                AlertMetric.PRICE_CHANGE_1D: [
                    {"kind": "PRICE", "target_id": rule.target_id}
                ]
            },
            asset_id=10,
        )


def test_run_cycle_creates_event_delivery_and_never_creates_signal(db: Session) -> None:
    now = datetime(2026, 7, 16, 3, 0, tzinfo=UTC)
    db.add(User(id=1, email="cycle@example.com", hashed_password="hash"))
    active = _rule(
        condition={"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": 3.0},
        delivery_policy="ONCE_PER_DAY",
    )
    active.id = 1
    active.channels = ["APP", "EMAIL"]
    paused = _rule(
        condition={"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": 3.0},
        delivery_policy="ONCE_PER_DAY",
        enabled=False,
    )
    paused.id = 2
    db.add_all([active, paused])
    db.commit()
    signal_count_before = db.scalar(select(func.count()).select_from(Signal))

    summary = AlertEngineService(db, snapshot_provider=_SnapshotProvider()).run_cycle(
        now=now
    )
    db.commit()

    event = db.scalars(select(AlertEvent)).one()
    deliveries = db.scalars(
        select(AlertDelivery).order_by(AlertDelivery.channel)
    ).all()
    deliveries_by_channel = {delivery.channel: delivery for delivery in deliveries}
    assert summary.evaluated_count == 1
    assert summary.emitted_count == 1
    assert event.rule_id == active.id
    assert event.asset_id == 10
    assert event.triggered_value["current"] == 4.0
    assert event.evidence == [{"kind": "PRICE", "target_id": "AAPL"}]
    assert set(deliveries_by_channel) == {"APP", "EMAIL"}
    app_delivery = deliveries_by_channel["APP"]
    assert app_delivery.alert_event_id == event.id
    assert app_delivery.status == "SUCCESS"
    assert app_delivery.delivered_at is not None
    assert app_delivery.delivered_at.replace(tzinfo=UTC) == now
    assert deliveries_by_channel["EMAIL"].status == "PENDING"
    assert deliveries_by_channel["EMAIL"].delivered_at is None
    assert active.last_triggered_at is not None
    assert active.last_triggered_at.replace(tzinfo=UTC) == now
    assert db.scalar(select(func.count()).select_from(Signal)) == signal_count_before

    second = AlertEngineService(db, snapshot_provider=_SnapshotProvider()).run_cycle(
        now=now + timedelta(minutes=1)
    )
    db.commit()

    assert second.emitted_count == 0
    assert second.deduplicated_count == 1
    assert db.scalar(select(func.count()).select_from(AlertEvent)) == 1


def test_metric_snapshot_provider_reads_persisted_domain_sources(db: Session) -> None:
    as_of = datetime(2026, 7, 16, 3, 0, tzinfo=UTC)
    user = User(id=1, email="provider@example.com", hashed_password="hash")
    asset = Asset(
        id=10,
        symbol="AAPL",
        name="Apple",
        market="NASDAQ",
    )
    watchlist = Watchlist(id=7, user_id=1, name="Growth")
    portfolio = Portfolio(
        id=9,
        user_id=1,
        name="Main",
        concentration_threshold=Decimal("0.4"),
        cash_balance=Decimal("0"),
    )
    db.add_all([user, asset, watchlist, portfolio])
    db.flush()
    db.add_all(
        [
            WatchlistItem(watchlist_id=7, asset_id=10, priority=0, tags=[]),
            Position(
                portfolio_id=9,
                asset_id=10,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("100"),
            ),
            EarningsEvent(
                symbol="AAPL",
                market="NASDAQ",
                event_date=date(2026, 7, 19),
                source="fixture",
            ),
            AssetSignalSnapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 15),
                signal_id=None,
                signal_type="WATCH",
                score=50,
                captured_at=as_of - timedelta(days=1),
            ),
            AssetSignalSnapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 16),
                signal_id=None,
                signal_type="RISK_ALERT",
                score=80,
                captured_at=as_of,
            ),
        ]
    )
    for offset, close in enumerate((Decimal("100"), Decimal("110"), Decimal("121"))):
        timestamp = as_of - timedelta(days=2 - offset)
        db.add(
            StockPriceBar(
                symbol="AAPL",
                market="NASDAQ",
                interval="1d",
                timestamp=timestamp,
                open_price=close,
                high_price=close,
                low_price=close,
                close_price=close,
                adjusted_close_price=close,
                volume=100,
                currency="USD",
                source="fixture",
            )
        )
    db.commit()
    provider = MetricSnapshotProvider(db)

    price_rule = _rule(
        condition={"metric": "PRICE_CHANGE_1D", "operator": "GTE", "value": 5.0}
    )
    price = provider.get_snapshot(price_rule, as_of=as_of)
    signal_rule = _rule(
        condition={"metric": "SIGNAL_CHANGED", "operator": "CHANGED", "value": None}
    )
    signal = provider.get_snapshot(signal_rule, as_of=as_of)
    earnings_rule = _rule(
        condition={"metric": "EARNINGS_DATE", "operator": "LTE", "value": 3}
    )
    earnings_rule.target_type = "WATCHLIST"
    earnings_rule.target_id = "7"
    earnings = provider.get_snapshot(earnings_rule, as_of=as_of)
    weight_rule = _rule(
        condition={"metric": "POSITION_WEIGHT", "operator": "GTE", "value": 0.15}
    )
    weight_rule.target_type = "PORTFOLIO"
    weight_rule.target_id = "9"
    weight = provider.get_snapshot(weight_rule, as_of=as_of)

    assert price.values[AlertMetric.PRICE_CHANGE_1D] == 10.0
    assert price.previous_values[AlertMetric.PRICE_CHANGE_1D] == 10.0
    assert signal.values[AlertMetric.SIGNAL_CHANGED] == "RISK_ALERT"
    assert signal.previous_values[AlertMetric.SIGNAL_CHANGED] == "WATCH"
    assert earnings.values[AlertMetric.EARNINGS_DATE] == 3
    assert earnings.asset_id == asset.id
    assert weight.values[AlertMetric.POSITION_WEIGHT] == 1.0
    assert weight.asset_id == asset.id


def test_only_topic_impact_score_is_unsupported() -> None:
    assert UNSUPPORTED_METRICS == frozenset({AlertMetric.TOPIC_IMPACT_SCORE})


@pytest.mark.parametrize(
    ("signal_type", "news_risk", "theme_heat", "ai_judgment"),
    [
        (SignalType.RISK_ALERT.value, "HIGH", "NEUTRAL", "RISK_INCREASING"),
        (SignalType.THESIS_BROKEN.value, "HIGH", "NEUTRAL", "RISK_INCREASING"),
        (SignalType.WATCH.value, "MEDIUM", "NEUTRAL", "WATCH"),
        (SignalType.SELL_REVIEW.value, "MEDIUM", "NEUTRAL", "WATCH"),
        (SignalType.OVERHEATED.value, "MEDIUM", "OVERHEATED", "WATCH"),
        (SignalType.BUY_CANDIDATE.value, "LOW", "NEUTRAL", "WATCH"),
        ("UNKNOWN", "LOW", "NEUTRAL", "STABLE"),
        (None, "LOW", "NEUTRAL", "STABLE"),
    ],
)
def test_signal_type_maps_to_derived_metrics(
    signal_type: str | None,
    news_risk: str,
    theme_heat: str,
    ai_judgment: str,
) -> None:
    assert _derive_signal_metrics(signal_type) == {
        AlertMetric.NEWS_RISK: news_risk,
        AlertMetric.THEME_HEAT: theme_heat,
        AlertMetric.AI_JUDGMENT_CHANGED: ai_judgment,
    }


def _signal_snapshot(
    *,
    asset_id: int,
    snapshot_date: date,
    signal_type: str | None,
) -> AssetSignalSnapshot:
    return AssetSignalSnapshot(
        asset_id=asset_id,
        snapshot_date=snapshot_date,
        signal_id=None,
        signal_type=signal_type,
        score=None,
        captured_at=datetime.combine(snapshot_date, datetime.min.time(), tzinfo=UTC),
    )


def test_derived_metric_aggregation_uses_max_and_any_previous() -> None:
    pairs = {
        20: (
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.OVERHEATED.value,
            ),
            None,
        ),
        10: (
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.BUY_CANDIDATE.value,
            ),
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.RISK_ALERT.value,
            ),
        ),
    }

    news = _aggregate_derived_metric(AlertMetric.NEWS_RISK, pairs)
    heat = _aggregate_derived_metric(AlertMetric.THEME_HEAT, pairs)

    assert news is not None
    assert heat is not None
    assert news[:3] == ("MEDIUM", "HIGH", True)
    assert news[4] == 20
    assert heat[:3] == ("OVERHEATED", "NEUTRAL", True)
    assert heat[4] == 20


def test_ai_judgment_aggregation_prefers_risk_then_lowest_asset_id() -> None:
    pairs = {
        20: (
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.RISK_ALERT.value,
            ),
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.WATCH.value,
            ),
        ),
        10: (
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.THESIS_BROKEN.value,
            ),
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.BUY_CANDIDATE.value,
            ),
        ),
        5: (
            _signal_snapshot(
                asset_id=5,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.WATCH.value,
            ),
            _signal_snapshot(
                asset_id=5,
                snapshot_date=date(2026, 7, 19),
                signal_type=None,
            ),
        ),
    }

    reading = _aggregate_derived_metric(
        AlertMetric.AI_JUDGMENT_CHANGED,
        pairs,
    )

    assert reading is not None
    current, previous, has_previous, evidence, asset_id = reading
    assert (current, previous, has_previous, asset_id) == (
        "RISK_INCREASING",
        "WATCH",
        True,
        10,
    )
    assert evidence == [
        {
            "kind": "SIGNAL_SNAPSHOT",
            "asset_id": 10,
            "snapshot_date": "2026-07-20",
            "signal_id": None,
            "score": None,
            "signal_type": "THESIS_BROKEN",
            "derived_metric": "AI_JUDGMENT_CHANGED",
            "derived_value": "RISK_INCREASING",
        }
    ]


def test_ai_judgment_aggregation_keeps_unchanged_history_unmatched() -> None:
    pairs = {
        10: (
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.RISK_ALERT.value,
            ),
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.THESIS_BROKEN.value,
            ),
        ),
        20: (
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.WATCH.value,
            ),
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.SELL_REVIEW.value,
            ),
        ),
    }

    reading = _aggregate_derived_metric(
        AlertMetric.AI_JUDGMENT_CHANGED,
        pairs,
    )

    assert reading is not None
    current, previous, has_previous, _, asset_id = reading
    assert (current, previous, has_previous, asset_id) == (
        "RISK_INCREASING",
        "RISK_INCREASING",
        True,
        10,
    )


def test_derived_metric_aggregation_omits_assets_without_snapshots() -> None:
    present = _signal_snapshot(
        asset_id=20,
        snapshot_date=date(2026, 7, 20),
        signal_type=None,
    )

    reading = _aggregate_derived_metric(
        AlertMetric.AI_JUDGMENT_CHANGED,
        {10: (None, None), 20: (present, None)},
    )

    assert reading is not None
    current, previous, has_previous, evidence, asset_id = reading
    assert (current, previous, has_previous, asset_id) == (
        "STABLE",
        "STABLE",
        False,
        20,
    )
    assert evidence[0]["asset_id"] == 20
    assert _aggregate_derived_metric(
        AlertMetric.NEWS_RISK,
        {10: (None, None), 20: (None, None)},
    ) is None


def test_provider_sources_derived_metrics_for_all_supported_targets(
    db: Session,
) -> None:
    as_of = datetime(2026, 7, 20, 3, 0, tzinfo=UTC)
    db.add(User(id=1, email="derived@example.com", hashed_password="hash"))
    db.add_all(
        [
            Asset(id=10, symbol="AAPL", name="Apple", market="NASDAQ"),
            Asset(id=20, symbol="MSFT", name="Microsoft", market="NASDAQ"),
            Asset(id=30, symbol="NVDA", name="Nvidia", market="NASDAQ"),
            Watchlist(id=7, user_id=1, name="Growth"),
            Watchlist(id=8, user_id=1, name="No snapshots"),
            Portfolio(
                id=9,
                user_id=1,
                name="Main",
                concentration_threshold=Decimal("0.4"),
                cash_balance=Decimal("0"),
            ),
        ]
    )
    db.flush()
    db.add_all(
        [
            WatchlistItem(watchlist_id=7, asset_id=10, priority=0, tags=[]),
            WatchlistItem(watchlist_id=7, asset_id=20, priority=1, tags=[]),
            WatchlistItem(watchlist_id=8, asset_id=30, priority=0, tags=[]),
            Position(
                portfolio_id=9,
                asset_id=10,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("100"),
            ),
            Position(
                portfolio_id=9,
                asset_id=30,
                quantity=Decimal("1"),
                avg_buy_price=Decimal("100"),
            ),
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 19),
                signal_type=SignalType.WATCH.value,
            ),
            _signal_snapshot(
                asset_id=10,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.RISK_ALERT.value,
            ),
            _signal_snapshot(
                asset_id=20,
                snapshot_date=date(2026, 7, 20),
                signal_type=SignalType.OVERHEATED.value,
            ),
        ]
    )
    db.commit()
    provider = MetricSnapshotProvider(db)
    evaluator = AlertEvaluator()

    symbol_rule = _rule(
        condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"}
    )
    symbol = provider.get_snapshot(symbol_rule, as_of=as_of)
    assert symbol.values[AlertMetric.NEWS_RISK] == "HIGH"
    assert symbol.previous_values[AlertMetric.NEWS_RISK] == "MEDIUM"
    assert symbol.asset_id == 10
    assert evaluator.evaluate_rule(symbol_rule, symbol).matched is True

    watchlist_rule = _rule(
        condition={
            "metric": "AI_JUDGMENT_CHANGED",
            "operator": "CHANGED",
            "value": None,
        }
    )
    watchlist_rule.target_type = "WATCHLIST"
    watchlist_rule.target_id = "7"
    watchlist = provider.get_snapshot(watchlist_rule, as_of=as_of)
    assert watchlist.values[AlertMetric.AI_JUDGMENT_CHANGED] == "RISK_INCREASING"
    assert watchlist.previous_values[AlertMetric.AI_JUDGMENT_CHANGED] == "WATCH"
    assert watchlist.asset_id == 10
    assert evaluator.evaluate_rule(watchlist_rule, watchlist).matched is True

    portfolio_rule = _rule(
        condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"}
    )
    portfolio_rule.target_type = "PORTFOLIO"
    portfolio_rule.target_id = "9"
    portfolio = provider.get_snapshot(portfolio_rule, as_of=as_of)
    assert portfolio.values[AlertMetric.NEWS_RISK] == "HIGH"
    assert portfolio.asset_id == 10
    assert evaluator.evaluate_rule(portfolio_rule, portfolio).matched is True

    default_rule = _rule(
        condition={
            "all": [
                {"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"},
                {
                    "metric": "THEME_HEAT",
                    "operator": "GTE",
                    "value": "OVERHEATED",
                },
                {
                    "metric": "AI_JUDGMENT_CHANGED",
                    "operator": "CHANGED",
                    "value": None,
                },
            ]
        }
    )
    default_rule.target_type = "WATCHLIST"
    default_rule.target_id = "8"
    default = provider.get_snapshot(default_rule, as_of=as_of)
    assert default.values == {}
    assert default.previous_values == {}
    assert default.asset_id is None
    assert default.evidence == {}
    result = evaluator.evaluate_rule(default_rule, default)
    assert result.matched is False
    assert result.unavailable_metrics == (
        "AI_JUDGMENT_CHANGED",
        "NEWS_RISK",
        "THEME_HEAT",
    )


def test_provider_keeps_actual_stable_snapshot_available(db: Session) -> None:
    as_of = datetime(2026, 7, 20, 3, 0, tzinfo=UTC)
    db.add(User(id=1, email="stable@example.com", hashed_password="hash"))
    db.add(Asset(id=10, symbol="AAPL", name="Apple", market="NASDAQ"))
    db.flush()
    db.add(
        _signal_snapshot(
            asset_id=10,
            snapshot_date=date(2026, 7, 20),
            signal_type=None,
        )
    )
    db.commit()
    rule = _rule(
        condition={"metric": "NEWS_RISK", "operator": "GTE", "value": "HIGH"}
    )

    snapshot = MetricSnapshotProvider(db).get_snapshot(rule, as_of=as_of)
    result = AlertEvaluator().evaluate_rule(rule, snapshot)

    assert snapshot.values == {AlertMetric.NEWS_RISK: "LOW"}
    assert snapshot.asset_id == 10
    assert result.matched is False
    assert result.unavailable_metrics == ()


def test_run_cycle_skips_topic_impact_score_as_unsupported(db: Session) -> None:
    db.add(User(id=1, email="unsupported@example.com", hashed_password="hash"))
    db.add(
        _rule(
            condition={
                "metric": "TOPIC_IMPACT_SCORE",
                "operator": "GTE",
                "value": 80,
            }
        )
    )
    db.commit()

    summary = AlertEngineService(db).run_cycle()

    assert summary.evaluated_count == 1
    assert summary.unsupported_count == 1
    assert summary.emitted_count == 0
    assert db.scalars(select(AlertEvent)).all() == []


def test_alert_worker_job_records_cycle_summary(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        def __init__(self, engine_db: Session) -> None:
            assert engine_db is db

        def run_cycle(self) -> AlertCycleSummary:
            return AlertCycleSummary(evaluated_count=2, emitted_count=1)

    monkeypatch.setattr(alert_jobs, "SessionLocal", lambda: db)
    monkeypatch.setattr(alert_jobs, "AlertEngineService", FakeEngine)

    alert_jobs.evaluate_alert_rules_job()

    job_run = db.scalars(select(JobRun)).one()
    assert job_run.job_type == "alert_evaluation"
    assert job_run.status == "success"
    assert job_run.metadata_ == {
        "evaluated_count": 2,
        "matched_count": 0,
        "emitted_count": 1,
        "deduplicated_count": 0,
        "unsupported_count": 0,
        "unavailable_count": 0,
    }
