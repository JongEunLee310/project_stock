"""create thesis checks and agent alert events

Revision ID: c3d4e5f60074
Revises: c3d4e5f60073
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f60074"
down_revision: str | None = "c3d4e5f60073"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "thesis_checks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "decision_id",
            sa.Integer(),
            sa.ForeignKey("decision_logs.id"),
            nullable=False,
        ),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("check_date", sa.Date(), nullable=False),
        sa.Column("verdict", sa.String(20), nullable=False),
        sa.Column("max_severity", sa.String(10), nullable=True),
        sa.Column("content", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "decision_id", "check_date", name="uq_thesis_checks_decision_date"
        ),
    )
    op.create_index(
        "ix_thesis_checks_user_date", "thesis_checks", ["user_id", "check_date"]
    )
    with op.batch_alter_table("alert_events") as batch_op:
        batch_op.add_column(
            sa.Column("source", sa.String(20), server_default="RULE", nullable=False)
        )
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    # 규칙 없는 이벤트는 기존 NOT NULL 스키마로 표현할 수 없어 전달 기록과 함께 삭제한다.
    op.execute(
        sa.text(
            "DELETE FROM alert_deliveries WHERE alert_event_id IN "
            "(SELECT id FROM alert_events WHERE rule_id IS NULL)"
        )
    )
    op.execute(sa.text("DELETE FROM alert_events WHERE rule_id IS NULL"))
    with op.batch_alter_table("alert_events") as batch_op:
        batch_op.alter_column("rule_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("source")
    op.drop_index("ix_thesis_checks_user_date", table_name="thesis_checks")
    op.drop_table("thesis_checks")
