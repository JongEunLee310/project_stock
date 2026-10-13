from collections.abc import Generator
from datetime import date

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domains.agents.thesis_watch.model import ThesisCheck
from app.domains.agents.thesis_watch.repository import ThesisCheckRepository
from app.domains.agents.thesis_watch.schema import ThesisCheckCreate
from app.domains.agents.thesis_watch.types import (
    FindingAspect,
    FindingRelation,
    ThesisVerdict,
)
from app.domains.assets.model import Asset
from app.domains.decision_logs.model import DecisionLog
from app.domains.users.model import User


@pytest.fixture
def thesis_db() -> Generator[Session, None, None]:
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()
        Base.metadata.create_all(connection)
        connection.commit()
        with Session(connection) as db:
            db.add_all(
                [
                    User(id=1, email="one@example.com", hashed_password="hash"),
                    User(id=2, email="two@example.com", hashed_password="hash"),
                    Asset(id=1, symbol="AAPL", name="Apple", market="NASDAQ"),
                ]
            )
            db.flush()
            db.add_all(
                [
                    DecisionLog(
                        id=i,
                        user_id=1 if i < 3 else 2,
                        target_type="SYMBOL",
                        target_id="AAPL",
                        decision_type="BUY",
                    )
                    for i in range(1, 4)
                ]
            )
            db.commit()
            yield db
    engine.dispose()


def check_data(
    decision_id: int = 1, day: int = 13, user_id: int = 1
) -> ThesisCheckCreate:
    return ThesisCheckCreate(
        user_id=user_id,
        decision_id=decision_id,
        asset_id=1,
        check_date=date(2026, 10, day),
        verdict=ThesisVerdict.MIXED,
        content={"headline": "점검", "findings": []},
    )


def test_repository_get_list_order_limit_and_rollback(thesis_db: Session) -> None:
    repo = ThesisCheckRepository(thesis_db)
    assert repo.get(1, date(2026, 10, 13)) is None
    older = repo.create(check_data(day=12))
    first = repo.create(check_data())
    second = repo.create(check_data(decision_id=2))
    repo.create(check_data(decision_id=3, user_id=2))
    assert first.created_at is not None
    assert first.max_severity is None
    assert first.verdict == "MIXED"
    assert first.content == {"headline": "점검", "findings": []}
    assert repo.get(1, date(2026, 10, 13)) is first
    assert repo.list_by_user(1, 10) == [second, first, older]
    assert repo.list_by_user(1, 1) == [second]
    assert repo.list_by_user(99, 10) == []
    thesis_db.rollback()
    assert thesis_db.scalars(select(ThesisCheck)).all() == []


def test_unique_decision_date(thesis_db: Session) -> None:
    repo = ThesisCheckRepository(thesis_db)
    repo.create(check_data())
    with pytest.raises(IntegrityError), thesis_db.begin_nested():
        repo.create(check_data())
    assert repo.get(1, date(2026, 10, 13)) is not None


@pytest.mark.parametrize("field", ["user_id", "decision_id", "asset_id"])
def test_foreign_keys(thesis_db: Session, field: str) -> None:
    data = check_data().model_copy(update={field: 999})
    with pytest.raises(IntegrityError), thesis_db.begin_nested():
        ThesisCheckRepository(thesis_db).create(data)


def test_enum_contract() -> None:
    assert {v.value for v in ThesisVerdict} == {
        "CHALLENGED",
        "MIXED",
        "SUPPORTED",
        "NO_RELEVANT_EVIDENCE",
    }
    assert {v.value for v in FindingRelation} == {"CHALLENGES", "SUPPORTS"}
    assert {v.value for v in FindingAspect} == {"THESIS", "RATIONALE", "RISK"}


def test_agent_non_dedup_integrity_error_preserves_transaction(
    thesis_db: Session,
) -> None:
    from datetime import UTC, datetime

    from app.domains.alert_events.model import AlertDelivery, AlertEvent
    from app.domains.alert_events.repository import AlertEventRepository

    repo = AlertEventRepository(thesis_db)
    asset = thesis_db.get(Asset, 1)
    assert asset is not None
    asset.name = "Pending change"
    with pytest.raises(IntegrityError):
        repo.create_agent_event(
            1, 999, "AAPL", "점검", "근거", "HIGH", [], "invalid", datetime.now(UTC)
        )
    assert thesis_db.is_active and asset.name == "Pending change"
    assert thesis_db.scalars(select(AlertEvent)).all() == []
    assert thesis_db.scalars(select(AlertDelivery)).all() == []
    event = repo.create_agent_event(
        1, 1, "AAPL", "점검", "근거", "HIGH", [], "valid", datetime.now(UTC)
    )
    assert event is not None
    thesis_db.rollback()
    assert thesis_db.scalars(select(AlertEvent)).all() == []
    thesis_db.refresh(asset)
    assert asset.name == "Apple"
