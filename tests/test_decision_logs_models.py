import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.orm import Mapper, Session

from app.domains.decision_logs.model import (
    DecisionEvidence,
    DecisionLog,
    DecisionReview,
    DecisionReviewTrigger,
    DecisionRisk,
    DecisionSnapshot,
)
from app.domains.decision_logs.types import (
    ConfidenceLevel,
    CreatedBy,
    DecisionStatus,
    DecisionType,
    EvidenceRelationship,
    OutcomeStatus,
    ReviewTriggerStatus,
    ReviewTriggerType,
    RiskSeverity,
    TargetType,
    ThesisResult,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_decision_log_enums_match_frozen_contract() -> None:
    assert [item.value for item in TargetType] == [
        "SYMBOL",
        "PORTFOLIO",
        "TOPIC",
        "SECTOR",
        "MARKET",
    ]
    assert [item.value for item in DecisionType] == [
        "WATCH",
        "RESEARCH_REQUIRED",
        "HOLD",
        "BUY_REVIEW",
        "SELL_REVIEW",
        "REDUCE_REVIEW",
        "REBALANCE_REVIEW",
        "THESIS_INVALIDATED",
        "NO_ACTION",
    ]
    assert [item.value for item in DecisionStatus] == [
        "DRAFT",
        "ACTIVE",
        "REVIEW_DUE",
        "REVIEWED",
        "CLOSED",
        "CANCELLED",
    ]
    assert [item.value for item in ConfidenceLevel] == ["LOW", "MEDIUM", "HIGH"]
    assert [item.value for item in EvidenceRelationship] == [
        "SUPPORTING",
        "CONTRADICTING",
        "RISK",
        "BACKGROUND",
    ]
    assert [item.value for item in RiskSeverity] == ["LOW", "MEDIUM", "HIGH"]
    assert [item.value for item in ReviewTriggerType] == [
        "DATE",
        "PRICE",
        "METRIC",
        "EVENT",
        "SIGNAL_CHANGE",
        "MANUAL",
    ]
    assert [item.value for item in ReviewTriggerStatus] == [
        "PENDING",
        "TRIGGERED",
        "DISMISSED",
    ]
    assert [item.value for item in CreatedBy] == ["USER", "AI", "SYSTEM"]
    assert [item.value for item in OutcomeStatus] == [
        "THESIS_CONFIRMED",
        "THESIS_PARTIALLY_CONFIRMED",
        "THESIS_INVALIDATED",
        "INSUFFICIENT_TIME",
        "CLOSED",
    ]
    assert [item.value for item in ThesisResult] == [
        "CONFIRMED",
        "PARTIALLY_CONFIRMED",
        "INVALIDATED",
    ]


def test_decision_log_models_round_trip_and_preserve_foreign_keys(db: Session) -> None:
    captured_at = datetime(2026, 7, 21, tzinfo=UTC)
    decision = DecisionLog(
        user_id=1,
        target_type=TargetType.SYMBOL.value,
        target_id="AAPL",
        symbol="AAPL",
        decision_type=DecisionType.BUY_REVIEW.value,
        thesis="서비스 매출이 성장한다.",
        rationale="마진과 자사주 매입을 확인했다.",
        confidence_level=ConfidenceLevel.HIGH.value,
    )
    db.add(decision)
    db.flush()
    db.add_all(
        [
            DecisionEvidence(
                decision_id=decision.id,
                evidence_type="RESEARCH",
                evidence_id="report-1",
                evidence_version=2,
                title="분기 리서치",
                summary="서비스 마진 개선",
                snapshot={"margin": 0.32},
                relationship=EvidenceRelationship.SUPPORTING.value,
            ),
            DecisionRisk(
                decision_id=decision.id,
                risk_type="VALUATION",
                description="멀티플 부담",
                severity=RiskSeverity.MEDIUM.value,
            ),
            DecisionReviewTrigger(
                decision_id=decision.id,
                trigger_type=ReviewTriggerType.DATE.value,
                condition={},
                scheduled_at=captured_at,
            ),
            DecisionSnapshot(
                decision_id=decision.id,
                snapshot_type="VALUATION",
                data={"forward_per": 28},
                captured_at=captured_at,
            ),
            DecisionReview(
                decision_id=decision.id,
                outcome_status=OutcomeStatus.THESIS_CONFIRMED.value,
                thesis_result=ThesisResult.CONFIRMED.value,
                process_quality={"evidence_sufficiency": 4},
                result_metrics={"return_rate": "0.12"},
                what_went_well="반대 근거를 확인했다.",
                what_was_missed="환율 변동",
                what_to_change="재검토 조건을 구체화한다.",
                reviewed_at=captured_at,
            ),
        ]
    )
    db.commit()

    stored = db.scalar(select(DecisionLog).where(DecisionLog.id == decision.id))
    assert stored is not None
    assert stored.target_type == "SYMBOL"
    assert stored.decision_type == "BUY_REVIEW"
    assert stored.status == "DRAFT"
    assert stored.created_by == "USER"
    assert db.scalar(select(DecisionEvidence)).relationship == "SUPPORTING"  # type: ignore[union-attr]
    assert db.scalar(select(DecisionRisk)).severity == "MEDIUM"  # type: ignore[union-attr]
    assert db.scalar(select(DecisionReviewTrigger)).status == "PENDING"  # type: ignore[union-attr]
    assert db.scalar(select(DecisionSnapshot)).data == {"forward_per": 28}  # type: ignore[union-attr]
    assert db.scalar(select(DecisionReview)).thesis_result == "CONFIRMED"  # type: ignore[union-attr]

    for model in (
        DecisionEvidence,
        DecisionRisk,
        DecisionReviewTrigger,
        DecisionSnapshot,
        DecisionReview,
    ):
        mapper = cast(Mapper[Any], inspect(model))
        decision_id_column = mapper.columns.decision_id
        assert {foreign_key.target_fullname for foreign_key in decision_id_column.foreign_keys} == {
            "decision_logs.id"
        }


def test_decision_log_migration_upgrade_and_downgrade() -> None:
    migration_path = (
        REPO_ROOT
        / "alembic"
        / "versions"
        / "c3d4e5f6006a_redesign_decision_logs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "c3d4e5f6006a_redesign_decision_logs",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE decision_logs ("
                "id INTEGER PRIMARY KEY, "
                "user_id INTEGER NOT NULL, "
                "ticker VARCHAR(20) NOT NULL, "
                "decision_type VARCHAR(30) NOT NULL, "
                "decided_at DATETIME NOT NULL"
                ")"
            )
        )
        operations = Operations(MigrationContext.configure(connection))
        original_op = cast(Any, migration).op
        cast(Any, migration).op = operations
        try:
            cast(Any, migration).upgrade()

            inspector = inspect(connection)
            assert {
                "decision_logs",
                "decision_evidence",
                "decision_risks",
                "decision_review_triggers",
                "decision_snapshots",
                "decision_reviews",
            }.issubset(inspector.get_table_names())
            assert {
                "target_type",
                "target_id",
                "symbol",
                "status",
                "superseded_by_id",
                "activated_at",
            }.issubset(
                {column["name"] for column in inspector.get_columns("decision_logs")}
            )

            cast(Any, migration).downgrade()

            inspector = inspect(connection)
            assert "decision_evidence" not in inspector.get_table_names()
            assert "ticker" in {
                column["name"] for column in inspector.get_columns("decision_logs")
            }
            assert "target_type" not in {
                column["name"] for column in inspector.get_columns("decision_logs")
            }
        finally:
            cast(Any, migration).op = original_op
