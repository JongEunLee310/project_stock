"""create_decision_logs

Revision ID: d4e5f6005701
Revises: c3d4e5f60056
Create Date: 2026-06-26 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d4e5f6005701"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60056"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
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
        sa.Column("cognitive_risks", sa.JSON(), server_default="[]", nullable=False),
        sa.Column(
            "created_by",
            sa.String(length=20),
            server_default="USER",
            nullable=False,
        ),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("decision_logs")
