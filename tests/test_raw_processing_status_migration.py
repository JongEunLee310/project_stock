import importlib.util
from pathlib import Path
from types import ModuleType

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect, text

from app.domains.ingestion.schema import ProcessingStatus


REPO_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    REPO_ROOT
    / "alembic"
    / "versions"
    / "c3d4e5f60058_add_raw_processing_status.py"
)


def _load_migration_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "test_c3d4e5f60058_add_raw_processing_status",
        MIGRATION_PATH,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_raw_processing_status_migration_up_down() -> None:
    migration = _load_migration_module()
    engine = create_engine("sqlite://")
    metadata = MetaData()
    raw_prices = Table(
        "raw_prices",
        metadata,
        Column("id", Integer, primary_key=True),
    )
    raw_news_events = Table(
        "raw_news_events",
        metadata,
        Column("id", Integer, primary_key=True),
    )

    with engine.begin() as connection:
        metadata.create_all(connection)
        connection.execute(raw_prices.insert().values(id=1))
        connection.execute(raw_news_events.insert().values(id=1))

        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = getattr(migration, "op")
        setattr(migration, "op", operations)
        try:
            upgrade = getattr(migration, "upgrade")
            downgrade = getattr(migration, "downgrade")

            upgrade()
            inspector = inspect(connection)
            raw_price_columns = {
                column["name"]: column for column in inspector.get_columns("raw_prices")
            }
            raw_news_columns = {
                column["name"]: column
                for column in inspector.get_columns("raw_news_events")
            }
            raw_price_indexes = {
                index["name"] for index in inspector.get_indexes("raw_prices")
            }
            raw_news_indexes = {
                index["name"] for index in inspector.get_indexes("raw_news_events")
            }

            assert raw_price_columns["processing_status"]["nullable"] is False
            assert raw_news_columns["processing_status"]["nullable"] is False
            assert "ix_raw_prices_processing_status" in raw_price_indexes
            assert "ix_raw_news_events_processing_status" in raw_news_indexes
            assert connection.scalar(
                text("select processing_status from raw_prices where id = 1")
            ) == ProcessingStatus.FETCHED.value
            assert connection.scalar(
                text("select processing_status from raw_news_events where id = 1")
            ) == ProcessingStatus.FETCHED.value

            downgrade()
            inspector = inspect(connection)
            raw_price_columns = {
                column["name"]: column for column in inspector.get_columns("raw_prices")
            }
            raw_news_columns = {
                column["name"]: column
                for column in inspector.get_columns("raw_news_events")
            }
            raw_price_indexes = {
                index["name"] for index in inspector.get_indexes("raw_prices")
            }
            raw_news_indexes = {
                index["name"] for index in inspector.get_indexes("raw_news_events")
            }
            assert "processing_status" not in raw_price_columns
            assert "processing_status" not in raw_news_columns
            assert "ix_raw_prices_processing_status" not in raw_price_indexes
            assert "ix_raw_news_events_processing_status" not in raw_news_indexes
        finally:
            setattr(migration, "op", original_op)
