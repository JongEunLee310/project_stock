import importlib.util
from collections.abc import Generator
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, cast

import pytest
import sqlalchemy as sa
from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.signals.model import Signal
from app.domains.signals.service import SignalService, build_change
from app.domains.signals.snapshot_model import AssetSignalSnapshot
from app.domains.signals.types import SignalType
from tests.conftest import TestingSessionLocal, api_data, set_current_user

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_MIGRATION = (
    REPO_ROOT / "alembic" / "versions" / "c3d4e5f60061_create_asset_signal_snapshots.py"
)


def _load_snapshot_migration() -> Any:
    spec = importlib.util.spec_from_file_location(
        "test_snapshot_migration",
        SNAPSHOT_MIGRATION,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextmanager
def _run_migration_with_ops(
    connection: sa.Connection,
    migration_module: Any,
) -> Generator[None, None, None]:
    context = MigrationContext.configure(connection)
    original_op = migration_module.op
    migration_module.op = Operations(context)
    try:
        yield
    finally:
        migration_module.op = original_op


def test_asset_signal_snapshots_migration_upgrade_downgrade_and_unique() -> None:
    engine = create_engine("sqlite://")
    migration = _load_snapshot_migration()
    with engine.begin() as connection:
        with _run_migration_with_ops(connection, migration):
            migration.upgrade()
            assert inspect(connection).has_table("asset_signal_snapshots")
            connection.execute(
                sa.text(
                    """
                    INSERT INTO asset_signal_snapshots
                    (asset_id, snapshot_date, signal_type, score, captured_at)
                    VALUES (1, '2026-07-10', 'WATCH', 50, '2026-07-10 00:00:00')
                    """
                )
            )
            with pytest.raises(IntegrityError):
                connection.execute(
                    sa.text(
                        """
                        INSERT INTO asset_signal_snapshots
                        (asset_id, snapshot_date, signal_type, score, captured_at)
                        VALUES (1, '2026-07-10', 'RISK_ALERT', 70, '2026-07-10 01:00:00')
                        """
                    )
                )
            migration.downgrade()
            assert not inspect(connection).has_table("asset_signal_snapshots")


def _add_asset(db: Session, symbol: str) -> Asset:
    asset = Asset(symbol=symbol, name=f"{symbol} Inc.", market="NASDAQ")
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def _add_signal(
    db: Session,
    asset_id: int,
    signal_type: str,
    score: int,
    expires_at: datetime | None = None,
) -> Signal:
    signal = Signal(
        asset_id=asset_id,
        signal_type=signal_type,
        score=score,
        risk_level="HIGH",
        reason="snapshot test signal",
        evidence=None,
        expires_at=expires_at,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


def _add_snapshot(
    db: Session,
    asset_id: int,
    snapshot_date: date,
    signal_type: str | None,
    score: int | None,
    signal_id: int | None = None,
    captured_at: datetime | None = None,
) -> AssetSignalSnapshot:
    snapshot = AssetSignalSnapshot(
        asset_id=asset_id,
        snapshot_date=snapshot_date,
        signal_id=signal_id,
        signal_type=signal_type,
        score=score,
        captured_at=captured_at
        or datetime.combine(snapshot_date, datetime.min.time(), tzinfo=timezone.utc),
    )
    db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return snapshot


def test_capture_daily_snapshot_records_each_asset_nulls_and_upserts(db: Session) -> None:
    active_asset = _add_asset(db, "AAPL")
    empty_asset = _add_asset(db, "MSFT")
    _add_signal(db, active_asset.id, SignalType.WATCH.value, 45)

    service = SignalService(db)
    captured = service.capture_daily_snapshot(date(2026, 7, 10))

    assert captured == 2
    snapshots = db.scalars(
        select(AssetSignalSnapshot).order_by(AssetSignalSnapshot.asset_id)
    ).all()
    assert len(snapshots) == 2
    assert snapshots[0].asset_id == active_asset.id
    assert snapshots[0].signal_type == SignalType.WATCH.value
    assert snapshots[0].score == 45
    assert snapshots[1].asset_id == empty_asset.id
    assert snapshots[1].signal_id is None
    assert snapshots[1].signal_type is None
    assert snapshots[1].score is None

    _add_signal(db, active_asset.id, SignalType.RISK_ALERT.value, 90)
    captured_again = service.capture_daily_snapshot(date(2026, 7, 10))

    assert captured_again == 2
    snapshots = db.scalars(select(AssetSignalSnapshot)).all()
    assert len(snapshots) == 2
    updated = db.scalars(
        select(AssetSignalSnapshot).where(
            AssetSignalSnapshot.asset_id == active_asset.id
        )
    ).one()
    assert updated.signal_type == SignalType.RISK_ALERT.value
    assert updated.score == 90


def _snapshot(signal_type: str | None, score: int | None) -> AssetSignalSnapshot:
    return AssetSignalSnapshot(
        asset_id=1,
        snapshot_date=date(2026, 7, 10),
        signal_type=signal_type,
        score=score,
        captured_at=datetime(2026, 7, 10, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("latest", "previous", "direction", "score_delta"),
    [
        (_snapshot(SignalType.WATCH.value, 40), None, "NEW", None),
        (_snapshot(SignalType.WATCH.value, 40), _snapshot(None, None), "NEW", None),
        (_snapshot(None, None), _snapshot(SignalType.WATCH.value, 40), "CLEARED", None),
        (
            _snapshot(SignalType.RISK_ALERT.value, 70),
            _snapshot(SignalType.WATCH.value, 50),
            "ESCALATED",
            20,
        ),
        (
            _snapshot(SignalType.WATCH.value, 50),
            _snapshot(SignalType.RISK_ALERT.value, 70),
            "DEESCALATED",
            -20,
        ),
        (
            _snapshot("CUSTOM_A", 70),
            _snapshot("CUSTOM_B", 50),
            "CHANGED",
            20,
        ),
        (
            _snapshot(SignalType.WATCH.value, 55),
            _snapshot(SignalType.WATCH.value, 50),
            "UNCHANGED",
            5,
        ),
    ],
)
def test_build_change_derives_direction_and_score_delta(
    latest: AssetSignalSnapshot,
    previous: AssetSignalSnapshot | None,
    direction: str,
    score_delta: int | None,
) -> None:
    change = build_change(latest, previous)

    assert change is not None
    assert change.direction == direction
    assert change.score_delta == score_delta


def test_current_view_embeds_change_and_all_view_is_unchanged(
    client: TestClient,
) -> None:
    set_current_user(1)
    asset_response = client.post(
        "/api/v1/assets",
        json={"symbol": "AAPL", "name": "Apple Inc.", "market": "NASDAQ"},
    )
    asset = cast(dict[str, Any], api_data(asset_response))
    signal_response = client.post(
        "/api/v1/signals",
        json={
            "asset_id": asset["id"],
            "signal_type": SignalType.RISK_ALERT.value,
            "score": 80,
            "risk_level": "HIGH",
            "reason": "risk increased",
        },
    )
    signal = cast(dict[str, Any], api_data(signal_response))

    no_snapshot_response = client.get("/api/v1/signals", params={"view": "current"})
    assert no_snapshot_response.status_code == 200
    no_snapshot_data = cast(list[dict[str, Any]], api_data(no_snapshot_response))
    assert no_snapshot_data[0]["change"] is None

    with TestingSessionLocal() as db:
        _add_snapshot(
            db,
            asset["id"],
            date(2026, 7, 9),
            SignalType.WATCH.value,
            50,
        )
        _add_snapshot(
            db,
            asset["id"],
            date(2026, 7, 10),
            SignalType.RISK_ALERT.value,
            80,
            signal["id"],
        )

    current_response = client.get("/api/v1/signals", params={"view": "current"})
    all_response = client.get("/api/v1/signals")

    current_data = cast(list[dict[str, Any]], api_data(current_response))
    assert current_data[0]["change"] == {
        "direction": "ESCALATED",
        "score_delta": 30,
        "previous_type": "WATCH",
        "previous_captured_at": "2026-07-09T00:00:00Z",
    }
    assert api_data(all_response) == [signal]


def test_signal_changes_endpoint_filters_orders_limits_and_since(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as db:
        first = _add_asset(db, "AAPL")
        second = _add_asset(db, "MSFT")
        _add_snapshot(db, first.id, date(2026, 7, 1), SignalType.WATCH.value, 40)
        _add_snapshot(db, first.id, date(2026, 7, 3), SignalType.RISK_ALERT.value, 80)
        _add_snapshot(db, first.id, date(2026, 7, 4), SignalType.RISK_ALERT.value, 85)
        _add_snapshot(db, second.id, date(2026, 7, 2), SignalType.BUY_CANDIDATE.value, 60)
        _add_snapshot(db, second.id, date(2026, 7, 5), None, None)

    response = client.get(
        "/api/v1/signals/changes",
        params={"since": "2026-07-03", "limit": 2},
    )

    assert response.status_code == 200
    data = cast(list[dict[str, Any]], api_data(response))
    assert [item["snapshot_date"] for item in data] == ["2026-07-05", "2026-07-03"]
    assert [item["change"]["direction"] for item in data] == ["CLEARED", "ESCALATED"]
    assert [item["asset"]["symbol"] for item in data] == ["MSFT", "AAPL"]
    assert data[0]["dominant"] is None


def test_signal_summary_endpoint_counts_categories_and_snapshot_delta(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as db:
        watch = _add_asset(db, "WATCH")
        risk = _add_asset(db, "RISK")
        buy = _add_asset(db, "BUY")
        research = _add_asset(db, "RESEARCH")
        _add_signal(db, watch.id, SignalType.WATCH.value, 30)
        _add_signal(db, risk.id, SignalType.RISK_ALERT.value, 80)
        _add_signal(db, buy.id, SignalType.BUY_CANDIDATE.value, 70)
        _add_signal(db, research.id, SignalType.SELL_REVIEW.value, 60)
        _add_snapshot(db, watch.id, date(2026, 7, 9), SignalType.WATCH.value, 30)
        _add_snapshot(db, risk.id, date(2026, 7, 9), SignalType.RISK_ALERT.value, 80)
        _add_snapshot(db, watch.id, date(2026, 7, 10), SignalType.RISK_ALERT.value, 90)
        _add_snapshot(db, risk.id, date(2026, 7, 10), SignalType.RISK_ALERT.value, 80)
        _add_snapshot(db, buy.id, date(2026, 7, 10), SignalType.BUY_CANDIDATE.value, 70)
        _add_snapshot(db, research.id, date(2026, 7, 10), None, None)

    response = client.get("/api/v1/signals/summary", params={"view": "current"})

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["total"] == 4
    assert data["by_category"] == {
        "WATCH": 1,
        "RISK": 1,
        "BUY": 1,
        "RESEARCH": 1,
    }
    assert data["delta_by_category"] == {
        "WATCH": -1,
        "RISK": 1,
        "BUY": 1,
        "RESEARCH": 0,
    }


def test_signal_summary_delta_is_zero_without_snapshot_pair(
    client: TestClient,
) -> None:
    set_current_user(1)
    with TestingSessionLocal() as db:
        asset = _add_asset(db, "AAPL")
        _add_signal(db, asset.id, SignalType.WATCH.value, 30)

    response = client.get("/api/v1/signals/summary", params={"view": "current"})

    assert response.status_code == 200
    data = cast(dict[str, Any], api_data(response))
    assert data["delta_by_category"] == {
        "WATCH": 0,
        "RISK": 0,
        "BUY": 0,
        "RESEARCH": 0,
    }
