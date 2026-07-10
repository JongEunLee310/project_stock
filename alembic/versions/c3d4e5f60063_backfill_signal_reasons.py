"""backfill_signal_reasons

Revision ID: c3d4e5f60063
Revises: c3d4e5f60062
Create Date: 2026-07-10 00:00:00.000000
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "c3d4e5f60063"
down_revision: str | Sequence[str] | None = "c3d4e5f60062"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


LEGACY_REASON_PREFIX = "High-impact news requires review: "


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            """
            SELECT id, reason, risk_level, evidence, key_points
            FROM signals
            WHERE reason LIKE :reason_pattern
            """
        ),
        {"reason_pattern": f"{LEGACY_REASON_PREFIX}%"},
    ).mappings()

    for row in rows:
        summary = row["reason"][len(LEGACY_REASON_PREFIX) :]
        impact_level = row["risk_level"]
        if impact_level is None:
            connection.execute(
                sa.text("UPDATE signals SET reason = :reason WHERE id = :signal_id"),
                {"reason": summary, "signal_id": row["id"]},
            )
            continue

        reason = f"영향도 {impact_level} 뉴스: {summary}"
        if row["key_points"] is not None:
            connection.execute(
                sa.text("UPDATE signals SET reason = :reason WHERE id = :signal_id"),
                {"reason": reason, "signal_id": row["id"]},
            )
            continue

        evidence = json.loads(row["evidence"]) if row["evidence"] is not None else {}
        key_points = [f"뉴스 영향도는 {impact_level}입니다."]
        sentiment = evidence.get("sentiment")
        if sentiment is not None:
            key_points.append(f"뉴스 감성은 {sentiment}입니다.")
        key_points.append(f"대상 뉴스 요지: {summary}")
        connection.execute(
            sa.text(
                """
                UPDATE signals
                SET reason = :reason, key_points = :key_points
                WHERE id = :signal_id
                """
            ),
            {
                "reason": reason,
                "key_points": json.dumps(key_points, ensure_ascii=False),
                "signal_id": row["id"],
            },
        )


def downgrade() -> None:
    """Backfill 전 데이터와 구분할 수 없어 역마이그레이션하지 않는다."""
