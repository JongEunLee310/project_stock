"""create_alert_candidates

Revision ID: c3d4e5f60055
Revises: c3d4e5f60054
Create Date: 2026-06-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3d4e5f60055"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f60054"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "alert_candidates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("candidate_type", sa.String(length=50), nullable=False),
        sa.Column("importance", sa.String(length=20), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="UNREAD",
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=True),
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
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_alert_candidates_asset_id",
        "alert_candidates",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        "ix_alert_candidates_candidate_type",
        "alert_candidates",
        ["candidate_type"],
        unique=False,
    )
    op.create_index(
        "ix_alert_candidates_importance",
        "alert_candidates",
        ["importance"],
        unique=False,
    )
    op.create_index(
        "ix_alert_candidates_status",
        "alert_candidates",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_alert_candidates_user_id",
        "alert_candidates",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_alert_candidates_user_id", table_name="alert_candidates")
    op.drop_index("ix_alert_candidates_status", table_name="alert_candidates")
    op.drop_index("ix_alert_candidates_importance", table_name="alert_candidates")
    op.drop_index("ix_alert_candidates_candidate_type", table_name="alert_candidates")
    op.drop_index("ix_alert_candidates_asset_id", table_name="alert_candidates")
    op.drop_table("alert_candidates")
