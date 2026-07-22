"""create news insights phase3 models

Revision ID: c3d4e5f6006d
Revises: c3d4e5f6006c
"""

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6006d"
down_revision: str | None = "c3d4e5f6006c"
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
        "fund_flow_outlooks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sector", sa.String(length=100), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("likelihood", sa.String(length=20), nullable=False),
        sa.Column("estimated_range", sa.String(length=100), nullable=True),
        sa.Column("horizon", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("key_assumptions", sa.JSON(), nullable=False),
        sa.Column("risk_factors", sa.JSON(), nullable=False),
        sa.Column("analysis_version", sa.String(length=100), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        _created_at_column(),
        _score_check("fund_flow_outlooks", "confidence"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_fund_flow_outlooks_analysis_version_sector",
        "fund_flow_outlooks",
        ["analysis_version", "sector"],
    )

    op.create_table(
        "fund_flow_scenarios",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("scenario_kind", sa.String(length=20), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("expected_flow_direction", sa.String(length=20), nullable=False),
        sa.Column("key_assumptions", sa.JSON(), nullable=False),
        sa.Column("benefiting_sectors", sa.JSON(), nullable=False),
        sa.Column("risk_sectors", sa.JSON(), nullable=False),
        sa.Column("related_symbols", sa.JSON(), nullable=False),
        sa.Column("invalidation_conditions", sa.JSON(), nullable=False),
        sa.Column("analysis_version", sa.String(length=100), nullable=False),
        _created_at_column(),
        _score_check("fund_flow_scenarios", "weight"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "analysis_version",
            "scenario_kind",
            name="uq_fund_flow_scenarios_topic_version_kind",
        ),
    )

    op.create_table(
        "topic_explanations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("analysis_version", sa.String(length=100), nullable=False),
        sa.Column("data_coverage", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("missing_data", sa.JSON(), nullable=False),
        sa.Column("limitations", sa.JSON(), nullable=False),
        sa.Column("already_priced_in", sa.Boolean(), nullable=False),
        sa.Column("already_priced_in_note", sa.Text(), nullable=True),
        sa.Column("last_updated", sa.DateTime(timezone=True), nullable=False),
        _created_at_column(),
        _score_check("topic_explanations", "data_coverage"),
        _score_check("topic_explanations", "confidence"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "analysis_version",
            name="uq_topic_explanations_topic_version",
        ),
    )

    op.create_table(
        "explanation_factors",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_explanation_id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("contribution_ratio", sa.Float(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        _score_check("explanation_factors", "contribution_ratio"),
        sa.ForeignKeyConstraint(
            ["topic_explanation_id"], ["topic_explanations.id"]
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("explanation_factors")
    op.drop_table("topic_explanations")
    op.drop_table("fund_flow_scenarios")
    op.drop_index(
        "ix_fund_flow_outlooks_analysis_version_sector",
        table_name="fund_flow_outlooks",
    )
    op.drop_table("fund_flow_outlooks")
