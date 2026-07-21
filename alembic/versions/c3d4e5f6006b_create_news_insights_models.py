"""create news insights models

Revision ID: c3d4e5f6006b
Revises: c3d4e5f6006a
"""

from collections.abc import Sequence
from typing import Any

from alembic import op
import sqlalchemy as sa

revision: str = "c3d4e5f6006b"
down_revision: str | None = "c3d4e5f6006a"
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
        "source_documents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("document_type", sa.String(length=30), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("source_url", sa.String(length=2048), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("raw_content", sa.Text(), nullable=False),
        sa.Column("normalized_content", sa.Text(), nullable=True),
        sa.Column("language", sa.String(length=10), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("source_reliability", sa.Float(), nullable=False),
        sa.Column(
            "processing_status",
            sa.String(length=20),
            server_default="PENDING",
            nullable=False,
        ),
        _created_at_column(),
        _score_check("source_documents", "source_reliability"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_source_documents_content_hash",
        "source_documents",
        ["content_hash"],
        unique=True,
    )
    op.create_index(
        "ix_source_documents_document_type_published_at",
        "source_documents",
        ["document_type", "published_at"],
    )

    op.create_table(
        "extracted_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("importance_score", sa.Float(), nullable=False),
        sa.Column("sentiment_direction", sa.String(length=20), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("primary_symbol", sa.String(length=20), nullable=True),
        sa.Column("sector_code", sa.String(length=50), nullable=True),
        sa.Column("event_fingerprint", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            server_default="ACTIVE",
            nullable=False,
        ),
        _created_at_column(),
        _score_check("extracted_events", "importance_score"),
        _score_check("extracted_events", "sentiment_score"),
        _score_check("extracted_events", "confidence_score"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_extracted_events_event_fingerprint",
        "extracted_events",
        ["event_fingerprint"],
    )

    op.create_table(
        "topic_clusters",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column("momentum_score", sa.Float(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=20), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=False),
        _created_at_column(),
        _score_check("topic_clusters", "momentum_score"),
        _score_check("topic_clusters", "sentiment_score"),
        _score_check("topic_clusters", "impact_score"),
        _score_check("topic_clusters", "confidence_score"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )

    op.create_table(
        "event_evidence",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("evidence_role", sa.String(length=20), nullable=False),
        sa.Column("extracted_quote", sa.Text(), nullable=True),
        _created_at_column(),
        _score_check("event_evidence", "relevance_score"),
        sa.ForeignKeyConstraint(["document_id"], ["source_documents.id"]),
        sa.ForeignKeyConstraint(["event_id"], ["extracted_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_event_evidence_event_id_evidence_role",
        "event_evidence",
        ["event_id", "evidence_role"],
    )

    op.create_table(
        "topic_keywords",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("keyword", sa.String(length=255), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False),
        sa.Column("sentiment_score", sa.Float(), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=True),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        _score_check("topic_keywords", "weight"),
        _score_check("topic_keywords", "sentiment_score"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_topic_keywords_topic_id",
        "topic_keywords",
        ["topic_id"],
    )

    op.create_table(
        "keyword_relations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("source_keyword", sa.String(length=255), nullable=False),
        sa.Column("target_keyword", sa.String(length=255), nullable=False),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("cooccurrence_count", sa.Integer(), nullable=False),
        _score_check("keyword_relations", "strength"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "topic_insights",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("executive_summary", sa.Text(), nullable=False),
        sa.Column("why_it_matters", sa.Text(), nullable=False),
        sa.Column("key_evidence", sa.JSON(), nullable=False),
        sa.Column("risk_points", sa.JSON(), nullable=False),
        sa.Column("counter_arguments", sa.JSON(), nullable=False),
        sa.Column("impact_score", sa.Float(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=False),
        sa.Column("model_name", sa.String(length=100), nullable=False),
        sa.Column("prompt_version", sa.String(length=100), nullable=False),
        _created_at_column(),
        _score_check("topic_insights", "impact_score"),
        _score_check("topic_insights", "confidence_score"),
        sa.ForeignKeyConstraint(["topic_id"], ["topic_clusters.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "version",
            name="uq_topic_insights_topic_version",
        ),
    )


def downgrade() -> None:
    op.drop_table("topic_insights")
    op.drop_table("keyword_relations")
    op.drop_index("ix_topic_keywords_topic_id", table_name="topic_keywords")
    op.drop_table("topic_keywords")
    op.drop_index(
        "ix_event_evidence_event_id_evidence_role",
        table_name="event_evidence",
    )
    op.drop_table("event_evidence")
    op.drop_table("topic_clusters")
    op.drop_index(
        "ix_extracted_events_event_fingerprint",
        table_name="extracted_events",
    )
    op.drop_table("extracted_events")
    op.drop_index(
        "ix_source_documents_document_type_published_at",
        table_name="source_documents",
    )
    op.drop_index(
        "ix_source_documents_content_hash",
        table_name="source_documents",
    )
    op.drop_table("source_documents")
