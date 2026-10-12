import importlib.util
import os
from collections.abc import Generator
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domains.assets.model import Asset
from app.domains.reports.model import ResearchReport
from app.domains.reports.repository import ResearchReportRepository
from app.domains.reports.schema import ResearchReportCreate
from app.domains.reports.types import ReportType
from app.domains.research_queue.repository import ResearchQueueRepository


def make_asset(db: Session, symbol: str = "AAPL") -> Asset:
    asset = Asset(symbol=symbol, name=symbol, market="NASDAQ")
    db.add(asset)
    db.flush()
    return asset


def test_create_defaults_to_article(db: Session) -> None:
    asset = make_asset(db)
    report = ResearchReportRepository(db).create(
        ResearchReportCreate(asset_id=asset.id, summary="기사 요약")
    )
    assert report.report_type == ReportType.ARTICLE.value
    assert report.brief_date is None
    assert report.content is None


def test_daily_brief_upsert_updates_same_row(db: Session) -> None:
    asset = make_asset(db)
    repo = ResearchReportRepository(db)
    content: dict[str, Any] = {"headline": "새 소식", "evidence": [{"item": "N1"}]}
    report = repo.upsert_daily_brief(asset.id, date(2026, 10, 12), "요약", "HIGH", {})
    report_id = report.id
    created_at = report.created_at
    old_updated_at = datetime(2020, 1, 1)
    report.updated_at = old_updated_at
    db.flush()

    updated = repo.upsert_daily_brief(
        asset.id, date(2026, 10, 12), "새 요약", None, content
    )
    assert updated is report
    assert updated.id == report_id
    assert updated.created_at == created_at
    assert updated.updated_at > old_updated_at
    assert repo.count_by_asset(asset.id) == 1
    db.expunge_all()
    loaded = db.get(ResearchReport, report_id)
    assert loaded is not None
    assert loaded.report_type == ReportType.DAILY_BRIEF.value
    assert loaded.brief_date == date(2026, 10, 12)
    assert loaded.summary == "새 요약"
    assert loaded.risk_level is None
    assert loaded.content == content


def test_daily_brief_upsert_does_not_commit(db: Session) -> None:
    asset = make_asset(db)
    db.commit()
    asset_id = asset.id
    repo = ResearchReportRepository(db)
    repo.upsert_daily_brief(asset_id, date(2026, 10, 12), "초안", None, {})
    db.rollback()
    assert repo.count_by_asset(asset_id) == 0

    report = repo.upsert_daily_brief(
        asset_id, date(2026, 10, 12), "저장된 요약", "HIGH", {"no_news": False}
    )
    db.commit()
    report_id = report.id
    repo.upsert_daily_brief(asset_id, date(2026, 10, 12), "수정안", None, {})
    db.rollback()
    loaded = db.get(ResearchReport, report_id)
    assert loaded is not None
    assert loaded.summary == "저장된 요약"
    assert loaded.risk_level == "HIGH"
    assert loaded.content == {"no_news": False}


def test_different_dates_and_assets_have_separate_briefs(db: Session) -> None:
    first = make_asset(db)
    second = make_asset(db, "MSFT")
    repo = ResearchReportRepository(db)
    reports = [
        repo.upsert_daily_brief(first.id, date(2026, 10, 12), "첫째", None, {}),
        repo.upsert_daily_brief(first.id, date(2026, 10, 13), "둘째", None, {}),
        repo.upsert_daily_brief(second.id, date(2026, 10, 12), "셋째", None, {}),
    ]
    assert len({report.id for report in reports}) == 3
    assert repo.count_by_asset(first.id) == 2
    assert repo.count_by_asset(second.id) == 1


@pytest.mark.parametrize(
    "backend", ["sqlite", pytest.param("postgres", marks=pytest.mark.postgres)]
)
def test_partial_unique_index(backend: str, request: pytest.FixtureRequest) -> None:
    db: Session = request.getfixturevalue(
        "db" if backend == "sqlite" else "postgres_reports_db"
    )
    asset = make_asset(db, uuid4().hex[:20])
    repo = ResearchReportRepository(db)
    brief_date = date(2026, 10, 12)
    report = repo.upsert_daily_brief(asset.id, brief_date, "브리프", "LOW", {})
    report_id = report.id
    updated = repo.upsert_daily_brief(asset.id, brief_date, "갱신", None, {})
    assert updated.id == report_id
    assert updated.summary == "갱신"
    assert updated.risk_level is None
    assert updated.content == {}
    for _ in range(2):
        db.add(ResearchReport(asset_id=asset.id, brief_date=brief_date, summary="기사"))
    db.flush()
    assert repo.count_by_asset(asset.id) == 3
    with pytest.raises(IntegrityError), db.begin_nested():
        db.add(
            ResearchReport(
                asset_id=asset.id,
                brief_date=brief_date,
                report_type=ReportType.DAILY_BRIEF.value,
                summary="중복 브리프",
            )
        )
        db.flush()
    assert repo.count_by_asset(asset.id) == 3


def test_latest_daily_brief_uses_creation_time(db: Session) -> None:
    asset = make_asset(db)
    other_asset = make_asset(db, "MSFT")
    repo = ResearchReportRepository(db)
    assert repo.get_latest_daily_brief(asset.id) is None
    now = datetime(2026, 10, 12, 12)
    first = repo.upsert_daily_brief(asset.id, date(2026, 10, 13), "첫째", None, {})
    first.created_at = now - timedelta(days=1)
    first.updated_at = now + timedelta(days=1)
    latest = repo.upsert_daily_brief(asset.id, date(2026, 10, 12), "둘째", None, {})
    latest.created_at = now
    article = ResearchReport(
        asset_id=asset.id, summary="기사", created_at=now + timedelta(days=2)
    )
    db.add(article)
    repo.upsert_daily_brief(other_asset.id, date(2026, 10, 12), "다른 종목", None, {})
    db.flush()
    assert repo.get_latest_daily_brief(asset.id) is latest
    assert repo.get_latest_daily_brief(other_asset.id) is not None


def test_daily_brief_is_included_in_research_queue(db: Session) -> None:
    asset = make_asset(db)
    repo = ResearchReportRepository(db)
    article = repo.create(ResearchReportCreate(asset_id=asset.id, summary="기사"))
    article.created_at = datetime(2026, 10, 11)
    brief = repo.upsert_daily_brief(asset.id, date(2026, 10, 12), "브리프", None, {})
    brief.created_at = datetime(2026, 10, 12)
    db.flush()
    presence = ResearchQueueRepository(db).get_data_presence_by_assets([asset])
    assert presence[asset.id].latest_report_at == brief.created_at


def test_daily_brief_migration_preserves_articles_and_round_trips() -> None:
    spec = importlib.util.spec_from_file_location(
        "daily_brief_migration",
        Path(__file__).resolve().parents[1]
        / "alembic/versions/c3d4e5f60071_add_daily_brief_report_fields.py",
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE research_reports "
                    "(id INTEGER PRIMARY KEY, asset_id INTEGER, summary TEXT)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO research_reports (asset_id, summary) VALUES (1, 'existing')"
                )
            )
            with Operations.context(MigrationContext.configure(connection)):
                migration.upgrade()
                row = (
                    connection.execute(text("SELECT * FROM research_reports"))
                    .mappings()
                    .one()
                )
                assert row["report_type"] == "ARTICLE"
                assert row["summary"] == "existing"
                assert row["brief_date"] is None
                assert row["content"] is None
                connection.execute(
                    text(
                        "INSERT INTO research_reports (asset_id, summary) VALUES (1, 'new')"
                    )
                )
                assert (
                    connection.scalar(
                        text(
                            "SELECT report_type FROM research_reports WHERE summary = 'new'"
                        )
                    )
                    == "ARTICLE"
                )
                connection.execute(
                    text(
                        "INSERT INTO research_reports (asset_id, summary, report_type, brief_date) "
                        "VALUES (1, 'brief', 'DAILY_BRIEF', '2026-10-12')"
                    )
                )
                with pytest.raises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO research_reports (asset_id, summary, report_type, brief_date) "
                            "VALUES (1, 'duplicate', 'DAILY_BRIEF', '2026-10-12')"
                        )
                    )
                migration.downgrade()
            assert {
                column["name"]
                for column in inspect(connection).get_columns("research_reports")
            } == {"id", "asset_id", "summary"}
            assert inspect(connection).get_indexes("research_reports") == []
            assert (
                connection.scalar(
                    text("SELECT summary FROM research_reports WHERE id = 1")
                )
                == "existing"
            )
    finally:
        engine.dispose()


@pytest.fixture
def postgres_reports_db() -> Generator[Session, None, None]:
    url = os.getenv("TEST_POSTGRES_URL")
    if not url:
        pytest.skip("TEST_POSTGRES_URL is not set")
    engine = create_engine(url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                with Session(
                    bind=connection, join_transaction_mode="create_savepoint"
                ) as session:
                    yield session
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
