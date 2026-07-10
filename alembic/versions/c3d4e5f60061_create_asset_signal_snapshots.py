"""create_asset_signal_snapshots

Revision ID: c3d4e5f60061
Revises: c3d4e5f60060
Create Date: 2026-07-10 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f60061"
down_revision: str | Sequence[str] | None = "c3d4e5f60060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_signal_snapshots",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column(
            "signal_id",
            sa.Integer(),
            sa.ForeignKey("signals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("signal_type", sa.String(20), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "asset_id",
            "snapshot_date",
            name="uq_asset_signal_snapshots_asset_date",
        ),
    )
    op.create_index(
        "ix_asset_signal_snapshots_asset_id",
        "asset_signal_snapshots",
        ["asset_id"],
    )
    op.create_index(
        "ix_asset_signal_snapshots_snapshot_date",
        "asset_signal_snapshots",
        ["snapshot_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_asset_signal_snapshots_snapshot_date",
        table_name="asset_signal_snapshots",
    )
    op.drop_index(
        "ix_asset_signal_snapshots_asset_id",
        table_name="asset_signal_snapshots",
    )
    op.drop_table("asset_signal_snapshots")
