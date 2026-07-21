import importlib.util
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, cast

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Table, create_engine, inspect, select
from sqlalchemy.orm import Mapper, Session

from app.domains.news_insights.model import (
    EventEvidence,
    ExtractedEvent,
    KeywordRelation,
    SourceDocument,
    TopicCluster,
    TopicInsight,
    TopicKeyword,
)
from app.domains.news_insights.seed import seed_mock_news_insights
from app.domains.news_insights.types import (
    DocumentType,
    EventStatus,
    EventType,
    EvidenceRole,
    ImportanceLevel,
    InvestorType,
    LifecycleStatus,
    ProcessingStatus,
    SentimentDirection,
    SymbolRelationship,
    TopicCategory,
)

def _enum_values(enum_type: type[Enum]) -> list[Any]:
    return [member.value for member in enum_type]


REPO_ROOT = Path(__file__).resolve().parents[1]
TABLE_NAMES = {
    "source_documents",
    "extracted_events",
    "event_evidence",
    "topic_clusters",
    "topic_keywords",
    "keyword_relations",
    "topic_insights",
}


def test_news_insight_enums_match_frozen_contract() -> None:
    expected: dict[type[Enum], list[str]] = {
        DocumentType: [
            "NEWS",
            "DISCLOSURE",
            "EARNINGS",
            "ANALYST_REPORT",
            "COMMUNITY",
            "COMPANY_IR",
        ],
        ProcessingStatus: ["PENDING", "NORMALIZED", "EXTRACTED", "FAILED"],
        EventType: [
            "EARNINGS_GUIDANCE",
            "BUYBACK",
            "REGULATION",
            "SUPPLY_CONTRACT",
            "MANAGEMENT_CHANGE",
            "ACCOUNTING_ISSUE",
            "PRODUCTION_DISRUPTION",
            "OTHER",
        ],
        SentimentDirection: ["POSITIVE", "NEUTRAL", "NEGATIVE", "MIXED"],
        ImportanceLevel: ["LOW", "MEDIUM", "HIGH"],
        EvidenceRole: ["PRIMARY", "SUPPORTING", "CONTRADICTING", "BACKGROUND"],
        LifecycleStatus: ["EMERGING", "RISING", "ACTIVE", "COOLING", "ARCHIVED"],
        EventStatus: ["ACTIVE", "MERGED", "DISMISSED"],
        TopicCategory: [
            "GROWTH",
            "REGULATION",
            "EARNINGS",
            "DEMAND",
            "MARKET_EVENT",
            "CAPITAL_POLICY",
            "SUPPLY_CHAIN",
        ],
        SymbolRelationship: ["DIRECT", "SUPPLY_CHAIN", "COMPETITOR", "CUSTOMER"],
        InvestorType: ["FOREIGN", "INSTITUTION", "RETAIL", "ETF"],
    }

    for enum_type, values in expected.items():
        assert _enum_values(enum_type) == values


def test_news_insight_models_define_foreign_keys_and_constraints() -> None:
    assert {
        SourceDocument.__tablename__,
        ExtractedEvent.__tablename__,
        EventEvidence.__tablename__,
        TopicCluster.__tablename__,
        TopicKeyword.__tablename__,
        KeywordRelation.__tablename__,
        TopicInsight.__tablename__,
    } == TABLE_NAMES

    foreign_keys = {
        EventEvidence: {
            "event_id": "extracted_events.id",
            "document_id": "source_documents.id",
        },
        TopicKeyword: {"topic_id": "topic_clusters.id"},
        KeywordRelation: {"topic_id": "topic_clusters.id"},
        TopicInsight: {"topic_id": "topic_clusters.id"},
    }
    for model, expected in foreign_keys.items():
        mapper = cast(Mapper[Any], inspect(model))
        for column_name, target in expected.items():
            column = mapper.columns[column_name]
            assert {key.target_fullname for key in column.foreign_keys} == {target}

    source_indexes = {
        str(index.name): index
        for index in cast(Table, SourceDocument.__table__).indexes
    }
    assert source_indexes["ix_source_documents_content_hash"].unique is True
    assert [
        column.name
        for column in source_indexes[
            "ix_source_documents_document_type_published_at"
        ].columns
    ] == ["document_type", "published_at"]
    event_indexes = {
        index.name for index in cast(Table, ExtractedEvent.__table__).indexes
    }
    assert "ix_extracted_events_event_fingerprint" in event_indexes
    assert any(
        constraint.name == "uq_topic_insights_topic_version"
        for constraint in cast(Table, TopicInsight.__table__).constraints
    )


def test_seed_mock_news_insights_inserts_connected_sample(db: Session) -> None:
    seeded = seed_mock_news_insights(
        db,
        now=datetime(2026, 7, 21, 12, tzinfo=UTC),
    )
    db.commit()

    assert len(seeded.topics) == 1
    assert db.scalar(select(SourceDocument)) is seeded.documents[0]
    assert db.scalar(select(ExtractedEvent)) is seeded.events[0]
    assert seeded.evidence[0].event_id == seeded.events[0].id
    assert seeded.evidence[0].document_id == seeded.documents[0].id
    assert seeded.insights[0].topic_id == seeded.topics[0].id
    assert seeded.insights[0].key_evidence == [{"event_id": seeded.events[0].id}]
    assert seeded.insights[0].counter_arguments


def test_news_insight_migration_upgrade_and_downgrade() -> None:
    migration_path = (
        REPO_ROOT
        / "alembic"
        / "versions"
        / "c3d4e5f6006b_create_news_insights_models.py"
    )
    spec = importlib.util.spec_from_file_location(
        "c3d4e5f6006b_create_news_insights_models",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        original_op = cast(Any, migration).op
        cast(Any, migration).op = operations
        try:
            cast(Any, migration).upgrade()
            inspector = inspect(connection)
            assert TABLE_NAMES <= set(inspector.get_table_names())
            assert any(
                index["name"] == "ix_extracted_events_event_fingerprint"
                for index in inspector.get_indexes("extracted_events")
            )
            assert any(
                constraint["name"] == "uq_topic_insights_topic_version"
                for constraint in inspector.get_unique_constraints("topic_insights")
            )

            cast(Any, migration).downgrade()
            assert TABLE_NAMES.isdisjoint(inspect(connection).get_table_names())
        finally:
            cast(Any, migration).op = original_op
