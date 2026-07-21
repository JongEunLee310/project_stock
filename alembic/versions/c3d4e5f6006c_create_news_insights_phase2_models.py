"""create news insights phase2 models

Revision ID: c3d4e5f6006c
Revises: c3d4e5f6006b
"""

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6006c"
down_revision: str | None = "c3d4e5f6006b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _created_at_column() -> "sa.Column[Any]":
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        server_default=sa.func.now(),
        nullable=False,
    )


def _score_check(table: str, column: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(
        f"{column} >= 0.0 AND {column} <= 1.0",
        name=f"ck_{table}_{column}_range",
    )


def upgrade() -> None:
    op.create_table(
        "investor_flows",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market", sa.String(length=30), nullable=True),
        sa.Column("topic_id", sa.Integer(), nullable=True),
        sa.Column("investor_type", sa.String(length=20), nullable=False),
        sa.Column("net_value", sa.Numeric(precision=20, scale=4), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("window", sa.String(length=30), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_kind", sa.String(length=30), nullable=False),
        _created_at_column(),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_investor_flows_topic_id_investor_type",
        "investor_flows",
        ["topic_id", "investor_type"],
    )

    op.create_table(
        "topic_symbol_sensitivity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=False),
        sa.Column("exposure_score", sa.Float(), nullable=False),
        sa.Column("impact_direction", sa.String(length=20), nullable=False),
        sa.Column("relationship", sa.String(length=30), nullable=False),
        sa.Column("valuation_burden", sa.String(length=20), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        _created_at_column(),
        _score_check("topic_symbol_sensitivity", "exposure_score"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "symbol",
            name="uq_topic_symbol_sensitivity_topic_symbol",
        ),
    )

    op.create_table(
        "market_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_kind", sa.String(length=30), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("symbol", sa.String(length=20), nullable=True),
        sa.Column("market", sa.String(length=30), nullable=True),
        sa.Column("importance_score", sa.Float(), nullable=False),
        _created_at_column(),
        _score_check("market_events", "importance_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_market_events_scheduled_at",
        "market_events",
        ["scheduled_at"],
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("processed_documents", sa.Integer(), nullable=False),
        sa.Column("extracted_events", sa.Integer(), nullable=False),
        sa.Column("active_topics", sa.Integer(), nullable=False),
        sa.Column("analysis_version", sa.String(length=100), nullable=False),
        _created_at_column(),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "market_event_topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("market_event_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["market_event_id"], ["market_events.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "market_event_id",
            "topic_id",
            name="uq_market_event_topics_event_topic",
        ),
    )

    op.create_table(
        "agent_run_stages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("agent_run_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("delayed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["agent_run_id"], ["agent_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "agent_run_id",
            "stage",
            name="uq_agent_run_stages_run_stage",
        ),
    )


def downgrade() -> None:
    op.drop_table("agent_run_stages")
    op.drop_table("market_event_topics")
    op.drop_table("agent_runs")
    op.drop_index("ix_market_events_scheduled_at", table_name="market_events")
    op.drop_table("market_events")
    op.drop_table("topic_symbol_sensitivity")
    op.drop_index(
        "ix_investor_flows_topic_id_investor_type",
        table_name="investor_flows",
    )
    op.drop_table("investor_flows")
