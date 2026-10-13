from datetime import date
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.domains.assets.model import Asset
from app.domains.knowledge.model import KnowledgeDocument
from app.domains.knowledge.repository import KnowledgeDocumentRepository
from app.domains.knowledge.schema import KnowledgeDocumentCreate
from app.domains.knowledge.types import KnowledgeKind


def data(
    external_id: str = "SEC:1:BUSINESS", **changes: object
) -> KnowledgeDocumentCreate:
    return KnowledgeDocumentCreate.model_validate(
        {
            "kind": KnowledgeKind.FILING_SECTION,
            "title": "연간보고서",
            "content": "사업 내용",
            "source_name": "SEC EDGAR",
            "source_url": "https://example.com/report",
            "external_id": external_id,
            "content_hash": "a" * 64,
            **changes,
        }
    )


def test_repository_queries_and_caller_transaction(db: Session) -> None:
    asset = Asset(symbol="A", name="A", market="NASDAQ")
    other = Asset(symbol="B", name="B", market="NASDAQ")
    db.add_all([asset, other])
    db.flush()
    repo = KnowledgeDocumentRepository(db)
    commit = Mock(wraps=db.commit)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(db, "commit", commit)
        undated = repo.add(data("undated", asset_id=asset.id))
        latest = repo.add(
            data("latest", asset_id=asset.id, effective_date=date(2026, 1, 1))
        )
        older = repo.add(
            data(
                "older",
                asset_id=asset.id,
                effective_date=date(2025, 1, 1),
                metadata_={"section": "BUSINESS"},
            )
        )
        tie = repo.add(data("tie", asset_id=asset.id, effective_date=date(2026, 1, 1)))
        repo.add(data("other", asset_id=other.id))
        assert repo.get_by_external_id(KnowledgeKind.FILING_SECTION, "latest") is latest
        assert repo.get_by_external_id(KnowledgeKind.FILING_SECTION, "missing") is None
        assert repo.list_after_id(undated.id, 2) == [latest, older]
        assert repo.list_by_asset(asset.id, KnowledgeKind.FILING_SECTION, 2) == [
            tie,
            latest,
        ]
        assert repo.list_by_asset(asset.id, KnowledgeKind.FILING_SECTION, 10) == [
            tie,
            latest,
            older,
            undated,
        ]
        assert undated.metadata_ == {}
        assert older.metadata_ == {"section": "BUSINESS"}
    commit.assert_not_called()
    db.rollback()
    assert repo.list_after_id(0, 10) == []


def test_unique_constraint(db: Session) -> None:
    repo = KnowledgeDocumentRepository(db)
    repo.add(data())
    with pytest.raises(IntegrityError):
        repo.add(data())
    db.rollback()


def test_model_foreign_key_and_server_metadata_default() -> None:
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(text("PRAGMA foreign_keys=ON"))
            Base.metadata.create_all(connection)
            with Session(connection) as session:
                document = KnowledgeDocument(**data().model_dump(exclude={"metadata_"}))
                session.add(document)
                session.flush()
                assert document.metadata_ == {}
                connection.execute(
                    text(
                        "INSERT INTO knowledge_documents "
                        "(kind, title, content, source_name, source_url, external_id, content_hash) "
                        "VALUES ('FILING_SECTION', 'title', 'body', 'SEC', 'url', 'raw', 'hash')"
                    )
                )
                assert (
                    session.scalar(
                        text(
                            "SELECT metadata FROM knowledge_documents WHERE external_id='raw'"
                        )
                    )
                    == "{}"
                )
                invalid = KnowledgeDocument(
                    **data("invalid", asset_id=999).model_dump()
                )
                session.add(invalid)
                with pytest.raises(IntegrityError):
                    session.flush()
    finally:
        engine.dispose()
