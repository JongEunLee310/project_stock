"""create_llm_analysis_runs

Revision ID: c3d4e5f60057
Revises: f6005703a129
Create Date: 2026-07-02 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60057"
down_revision: Union[str, Sequence[str], None] = "f6005703a129"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llm_analysis_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("task_type", sa.String(length=50), nullable=False),
        sa.Column("related_symbols", sa.JSON(), nullable=False),
        sa.Column("input_context_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=True),
        sa.Column("related_decision_log_id", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["related_decision_log_id"], ["decision_logs.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_llm_analysis_runs_related_decision_log_id",
        "llm_analysis_runs",
        ["related_decision_log_id"],
        unique=False,
    )
    op.create_index(
        "ix_llm_analysis_runs_status",
        "llm_analysis_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_llm_analysis_runs_task_type",
        "llm_analysis_runs",
        ["task_type"],
        unique=False,
    )
    op.create_index(
        "ix_llm_analysis_runs_user_id",
        "llm_analysis_runs",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_llm_analysis_runs_user_id", table_name="llm_analysis_runs")
    op.drop_index("ix_llm_analysis_runs_task_type", table_name="llm_analysis_runs")
    op.drop_index("ix_llm_analysis_runs_status", table_name="llm_analysis_runs")
    op.drop_index(
        "ix_llm_analysis_runs_related_decision_log_id",
        table_name="llm_analysis_runs",
    )
    op.drop_table("llm_analysis_runs")
