"""merge_watchlists_and_theses_heads

Revision ID: 8c3f0d2b7a91
Revises: 2b8a4e9c1f03, 4d1c6a7e8b20
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "8c3f0d2b7a91"
down_revision: Union[str, Sequence[str], None] = (
    "2b8a4e9c1f03",
    "4d1c6a7e8b20",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
