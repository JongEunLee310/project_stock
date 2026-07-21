"""redesign decision logs as a structured journal

Revision ID: c3d4e5f6006a
Revises: c3d4e5f60069

기존 데이터는 테스트·mock 수준이라는 ADR-016의 전제에 따라 이관하지 않고 테이블을
재생성한다. 기존 필드의 개념 매핑은 ticker -> symbol/target_id, reason -> rationale,
decision_status -> status, cognitive_risks -> decision_risks이다.
"""

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6006a"
down_revision: str | None = "c3d4e5f60069"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _drop_llm_analysis_reference() -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "llm_analysis_runs" not in inspector.get_table_names():
        return False

    op.execute(
        sa.text(
            "UPDATE llm_analysis_runs "
            "SET related_decision_log_id = NULL "
            "WHERE related_decision_log_id IS NOT NULL"
        )
    )
    if bind.dialect.name == "sqlite":
        return False

    for foreign_key in inspector.get_foreign_keys("llm_analysis_runs"):
        if foreign_key["constrained_columns"] == ["related_decision_log_id"]:
            constraint_name = foreign_key["name"]
            if constraint_name is not None:
                op.drop_constraint(
                    constraint_name,
                    "llm_analysis_runs",
                    type_="foreignkey",
                )
                return True
    return False


def _restore_llm_analysis_reference(was_dropped: bool) -> None:
    if was_dropped:
        op.create_foreign_key(
            "llm_analysis_runs_related_decision_log_id_fkey",
            "llm_analysis_runs",
            "decision_logs",
            ["related_decision_log_id"],
            ["id"],
        )


def _timestamp_columns() -> tuple[sa.Column[Any], sa.Column[Any]]:
    return (
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def _create_redesigned_tables() -> None:
    op.create_table(
        "decision_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(length=20), nullable=False),
        sa.Column("target_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("decision_type", sa.String(length=30), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="DRAFT",
            nullable=False,
        ),
        sa.Column("thesis", sa.Text(), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("confidence_level", sa.String(length=10), nullable=True),
        sa.Column(
            "created_by",
            sa.String(length=20),
            server_default="USER",
            nullable=False,
        ),
        sa.Column("superseded_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["superseded_by_id"], ["decision_logs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column("evidence_id", sa.String(length=64), nullable=True),
        sa.Column("evidence_version", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("relationship", sa.String(length=20), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["decision_id"], ["decision_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_risks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("risk_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=10), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["decision_id"], ["decision_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_review_triggers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("condition", sa.JSON(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["decision_id"], ["decision_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("snapshot_type", sa.String(length=30), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["decision_id"], ["decision_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "decision_reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_id", sa.Integer(), nullable=False),
        sa.Column("outcome_status", sa.String(length=30), nullable=False),
        sa.Column("thesis_result", sa.String(length=30), nullable=False),
        sa.Column("process_quality", sa.JSON(), nullable=True),
        sa.Column("result_metrics", sa.JSON(), nullable=True),
        sa.Column("what_went_well", sa.Text(), nullable=True),
        sa.Column("what_was_missed", sa.Text(), nullable=True),
        sa.Column("what_to_change", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["decision_id"], ["decision_logs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def _create_legacy_decision_logs() -> None:
    op.create_table(
        "decision_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("ticker", sa.String(length=20), nullable=False),
        sa.Column("company_name", sa.String(length=255), nullable=True),
        sa.Column("decision_type", sa.String(length=30), nullable=False),
        sa.Column(
            "decision_status",
            sa.String(length=20),
            server_default="OPEN",
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("risk_note", sa.Text(), nullable=True),
        sa.Column("action_plan", sa.Text(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("target_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("stop_loss_price", sa.Numeric(20, 4), nullable=True),
        sa.Column("valuation_snapshot", sa.JSON(), nullable=True),
        sa.Column("news_snapshot", sa.JSON(), nullable=True),
        sa.Column("portfolio_snapshot", sa.JSON(), nullable=True),
        sa.Column("ai_analysis_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "cognitive_risks",
            sa.JSON(),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "created_by",
            sa.String(length=20),
            server_default="USER",
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamp_columns(),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def upgrade() -> None:
    llm_reference_was_dropped = _drop_llm_analysis_reference()
    op.drop_table("decision_logs")
    _create_redesigned_tables()
    _restore_llm_analysis_reference(llm_reference_was_dropped)


def downgrade() -> None:
    op.drop_table("decision_reviews")
    op.drop_table("decision_snapshots")
    op.drop_table("decision_review_triggers")
    op.drop_table("decision_risks")
    op.drop_table("decision_evidence")
    llm_reference_was_dropped = _drop_llm_analysis_reference()
    op.drop_table("decision_logs")
    _create_legacy_decision_logs()
    _restore_llm_analysis_reference(llm_reference_was_dropped)
