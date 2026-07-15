import importlib.util
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

import app.db.models  # noqa: F401 — registers all models before create_all
from app.domains.alert_events.model import AlertDelivery, AlertEvent
from app.domains.alert_events.types import AlertDeliveryStatus, AlertEventStatus
from app.domains.alert_rules.model import AlertRule
from app.domains.alert_rules.types import (
    AlertChannel,
    AlertDeliveryPolicy,
    AlertMetric,
    AlertOperator,
    AlertRuleSource,
    AlertSeverity,
    AlertTargetType,
    AlertTemplateType,
)
from app.domains.notification_channels.model import NotificationChannel
from app.domains.users.model import User

REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "c3d4e5f60069_create_alert_unified_models.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_c3d4e5f60069_create_alert_unified_models",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _add_user(db: Session, email: str = "alerts@example.com") -> User:
    user = User(email=email, hashed_password="test-hash")
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _add_rule(db: Session, user_id: int) -> AlertRule:
    rule = AlertRule(
        user_id=user_id,
        name="High news risk",
        source=AlertRuleSource.USER.value,
        template_type=AlertTemplateType.NEWS_RISK_HIGH.value,
        target_type=AlertTargetType.SYMBOL.value,
        target_id="NVDA",
        condition={
            "metric": AlertMetric.NEWS_RISK.value,
            "operator": AlertOperator.GTE.value,
            "value": "HIGH",
        },
        severity=AlertSeverity.HIGH.value,
        channels=[AlertChannel.APP.value],
        cooldown_seconds=3600,
        delivery_policy=AlertDeliveryPolicy.ONCE_PER_TRANSITION.value,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


def test_alert_unified_enum_values_match_design() -> None:
    assert [member.value for member in AlertRuleSource] == ["SYSTEM", "USER"]
    assert [member.value for member in AlertTargetType] == [
        "SYMBOL",
        "WATCHLIST",
        "PORTFOLIO",
        "TOPIC",
        "MARKET",
    ]
    assert [member.value for member in AlertMetric] == [
        "NEWS_RISK",
        "PRICE_CHANGE_1D",
        "SIGNAL_CHANGED",
        "AI_JUDGMENT_CHANGED",
        "THEME_HEAT",
        "POSITION_WEIGHT",
        "EARNINGS_DATE",
        "TOPIC_IMPACT_SCORE",
    ]
    assert [member.value for member in AlertOperator] == ["EQ", "GTE", "LTE", "CHANGED"]
    assert [member.value for member in AlertSeverity] == [
        "LOW",
        "MEDIUM",
        "HIGH",
        "CRITICAL",
    ]
    assert [member.value for member in AlertChannel] == [
        "APP",
        "EMAIL",
        "DISCORD",
        "SLACK",
    ]
    assert [member.value for member in AlertDeliveryPolicy] == [
        "ONCE_PER_TRANSITION",
        "ONCE_PER_DAY",
    ]
    assert [member.value for member in AlertTemplateType] == [
        "HOLDING_NEWS_RISK",
        "WATCHLIST_AI_JUDGMENT",
        "EARNINGS_D3",
        "POSITION_WEIGHT_OVER",
        "NEWS_RISK_HIGH",
        "TOPIC_IMPACT_SURGE",
    ]
    assert [member.value for member in AlertDeliveryStatus] == [
        "PENDING",
        "SUCCESS",
        "FAILED",
    ]
    assert [member.value for member in AlertEventStatus] == ["UNREAD", "READ"]


def test_alert_unified_models_create_with_defaults(db: Session) -> None:
    user = _add_user(db)
    rule = _add_rule(db, user.id)
    event = AlertEvent(
        rule_id=rule.id,
        user_id=user.id,
        target_type=rule.target_type,
        target_id=rule.target_id,
        title="News risk increased",
        message="NVDA news risk is now high.",
        severity=AlertSeverity.HIGH.value,
        triggered_value={"current": "HIGH", "threshold": "HIGH"},
        evidence=[{"kind": "news", "title": "Example"}],
        dedup_key="rule:1:NVDA:high",
    )
    db.add(event)
    db.flush()
    delivery = AlertDelivery(
        alert_event_id=event.id,
        channel=AlertChannel.APP.value,
    )
    notification_channel = NotificationChannel(
        user_id=user.id,
        channel_type=AlertChannel.APP.value,
        configuration={},
    )
    db.add_all([delivery, notification_channel])
    db.commit()
    db.refresh(rule)
    db.refresh(event)
    db.refresh(delivery)
    db.refresh(notification_channel)

    assert rule.enabled is True
    assert isinstance(rule.created_at, datetime)
    assert isinstance(rule.updated_at, datetime)
    assert event.read_at is None
    assert isinstance(event.triggered_at, datetime)
    assert delivery.status == AlertDeliveryStatus.PENDING.value
    assert isinstance(delivery.attempted_at, datetime)
    assert delivery.delivered_at is None
    assert delivery.error_code is None
    assert notification_channel.enabled is True
    assert notification_channel.verified_at is None


def test_alert_event_rejects_duplicate_user_dedup_key(db: Session) -> None:
    user = _add_user(db, "dedup@example.com")
    rule = _add_rule(db, user.id)

    def build_event(title: str) -> AlertEvent:
        return AlertEvent(
            rule_id=rule.id,
            user_id=user.id,
            target_type=AlertTargetType.SYMBOL.value,
            target_id="NVDA",
            title=title,
            message="Duplicate event test.",
            severity=AlertSeverity.HIGH.value,
            triggered_value={"current": "HIGH"},
            evidence=[],
            dedup_key="same-dedup-key",
        )

    db.add(build_event("First"))
    db.commit()
    db.add(build_event("Second"))

    with pytest.raises(IntegrityError):
        db.commit()


def test_alert_unified_migration_upgrade_and_downgrade() -> None:
    migration = _load_migration_module()
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE assets (id INTEGER PRIMARY KEY)"))
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = getattr(migration, "op")
        setattr(migration, "op", operations)
        try:
            upgrade = getattr(migration, "upgrade")
            downgrade = getattr(migration, "downgrade")
            upgrade()

            inspector = inspect(connection)
            assert {
                "alert_rules",
                "alert_events",
                "alert_deliveries",
                "notification_channels",
            }.issubset(inspector.get_table_names())
            unique_constraints = inspector.get_unique_constraints("alert_events")
            assert {
                "name": "uq_alert_events_user_dedup",
                "column_names": ["user_id", "dedup_key"],
            } in unique_constraints

            downgrade()
            remaining_tables = inspect(connection).get_table_names()
            assert "alert_rules" not in remaining_tables
            assert "alert_events" not in remaining_tables
            assert "alert_deliveries" not in remaining_tables
            assert "notification_channels" not in remaining_tables
        finally:
            setattr(migration, "op", original_op)
