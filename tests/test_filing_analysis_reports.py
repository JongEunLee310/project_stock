from datetime import datetime, timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.domains.assets.model import Asset
from app.domains.reports.model import ResearchReport
from app.domains.reports.repository import ResearchReportRepository
from app.domains.reports.schema import ResearchReportResponse
from app.domains.reports.types import ReportType

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c3d4e5f60073"
PREVIOUS = "c3d4e5f60072"


def make_asset(db: Session, symbol: str = "AAPL") -> Asset:
    asset = Asset(symbol=symbol, name=symbol, market="NASDAQ")
    db.add(asset)
    db.flush()
    return asset


def test_create_lookup_and_rollback(db: Session) -> None:
    asset = make_asset(db)
    db.commit()
    asset_id = asset.id
    repo = ResearchReportRepository(db)
    assert (
        repo.get_by_source_ref(asset_id, ReportType.FILING_ANALYSIS, "edgar:new")
        is None
    )
    report = repo.create_filing_analysis(
        asset_id, "edgar:new", "headline", "HIGH", {"evidence": ["M1"]}
    )
    assert report.id is not None
    assert report.summary == "headline"
    assert report.risk_level == "HIGH"
    assert report.content == {"evidence": ["M1"]}
    assert report.report_type == ReportType.FILING_ANALYSIS.value
    assert (
        repo.get_by_source_ref(asset_id, ReportType.FILING_ANALYSIS, "edgar:new")
        is report
    )
    assert repo.get_by_source_ref(asset_id, ReportType.ARTICLE, "edgar:new") is None
    assert (
        repo.get_by_source_ref(asset_id + 1, ReportType.FILING_ANALYSIS, "edgar:new")
        is None
    )
    assert (
        "source_ref" not in ResearchReportResponse.model_validate(report).model_dump()
    )
    db.rollback()
    assert repo.count_by_asset(asset_id) == 0


def test_partial_unique_and_nulls(db: Session) -> None:
    asset, other = make_asset(db), make_asset(db, "MSFT")
    repo = ResearchReportRepository(db)
    repo.create_filing_analysis(asset.id, "edgar:new", "first", None, {})
    repo.create_filing_analysis(other.id, "edgar:new", "other", None, {})
    db.add(ResearchReport(asset_id=asset.id, source_ref="edgar:new", summary="article"))
    for _ in range(2):
        db.add(
            ResearchReport(
                asset_id=asset.id,
                report_type=ReportType.FILING_ANALYSIS.value,
                summary="null",
            )
        )
    db.flush()
    with pytest.raises(IntegrityError), db.begin_nested():
        repo.create_filing_analysis(asset.id, "edgar:new", "duplicate", None, {})
    assert repo.count_by_asset(asset.id) == 4


def test_created_between_boundaries_and_order(db: Session) -> None:
    asset, other = make_asset(db), make_asset(db, "MSFT")
    repo = ResearchReportRepository(db)
    start = datetime(2026, 10, 12)
    end = start + timedelta(days=1)
    reports = [
        repo.create_filing_analysis(asset.id, f"edgar:{i}", str(i), None, {})
        for i in range(5)
    ]
    for report, timestamp in zip(
        reports,
        [
            end,
            start,
            end + timedelta(seconds=1),
            start + timedelta(hours=1),
            start - timedelta(seconds=1),
        ],
        strict=True,
    ):
        report.created_at = timestamp
    repo.create_filing_analysis(
        other.id, "edgar:other", "other", None, {}
    ).created_at = end
    db.add(ResearchReport(asset_id=asset.id, summary="article", created_at=end))
    db.flush()
    assert repo.list_filing_analyses_created_between(asset.id, start, end) == [
        reports[3],
        reports[0],
    ]
    assert repo.list_filing_analyses_created_between(asset.id, end, end) == []


def test_single_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == ["c3d4e5f60074"]
    revision = script.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS


@pytest.mark.parametrize("upgrade", [True, False])
def test_postgres_offline_migration(
    upgrade: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/offline")
    monkeypatch.setattr("logging.config.fileConfig", Mock())
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    if upgrade:
        command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
        sql = output.getvalue()
        assert "ADD COLUMN source_ref VARCHAR(200)" in sql
        assert (
            "CREATE UNIQUE INDEX uq_research_reports_source_ref ON research_reports "
            "(asset_id, report_type, source_ref) WHERE source_ref IS NOT NULL"
        ) in sql
    else:
        command.downgrade(config, f"{REVISION}:{PREVIOUS}", sql=True)
        sql = output.getvalue()
        assert sql.index("DROP INDEX") < sql.index("DROP COLUMN source_ref")


def test_sqlite_migration_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revision = script.get_revision(REVISION)
    assert revision is not None
    migration = revision.module
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                "CREATE TABLE research_reports (id INTEGER PRIMARY KEY, "
                "asset_id INTEGER, report_type VARCHAR(20), summary TEXT)"
            )
            connection.exec_driver_sql(
                "INSERT INTO research_reports VALUES (1, 1, 'ARTICLE', 'existing')"
            )
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            for _ in range(2):
                migration.upgrade()
                assert connection.exec_driver_sql(
                    "SELECT summary, source_ref FROM research_reports WHERE id = 1"
                ).one() == ("existing", None)
                connection.exec_driver_sql(
                    "INSERT INTO research_reports (asset_id, report_type, source_ref) "
                    "VALUES (1, 'FILING_ANALYSIS', 'edgar:new')"
                )
                with pytest.raises(IntegrityError):
                    connection.exec_driver_sql(
                        "INSERT INTO research_reports (asset_id, report_type, source_ref) "
                        "VALUES (1, 'FILING_ANALYSIS', 'edgar:new')"
                    )
                for _ in range(2):
                    connection.exec_driver_sql(
                        "INSERT INTO research_reports (asset_id, report_type) "
                        "VALUES (1, 'FILING_ANALYSIS')"
                    )
                migration.downgrade()
                assert "source_ref" not in {
                    column["name"]
                    for column in inspect(connection).get_columns("research_reports")
                }
                assert not inspect(connection).get_indexes("research_reports")
    finally:
        engine.dispose()
