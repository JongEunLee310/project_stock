"""merge_news_and_jobs_heads

Revision ID: 4d5e6f708192
Revises: 2b3c4d5e6f70, 3c4d5e6f7081
Create Date: 2026-06-18 00:00:00.000000

"""
from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = "4d5e6f708192"
down_revision: Union[str, Sequence[str], None] = (
    "2b3c4d5e6f70",
    "3c4d5e6f7081",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
