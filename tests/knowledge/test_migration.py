from io import StringIO
from pathlib import Path
from typing import cast
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Table, create_engine, inspect

from app.core.config import settings
from app.domains.knowledge.model import KnowledgeDocument

ROOT = Path(__file__).resolve().parents[2]
REVISION = "c3d4e5f60072"
PREVIOUS = "c3d4e5f60071"


def test_single_head_and_model_constraints() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS
    table = cast(Table, KnowledgeDocument.__table__)
    assert {fk.target_fullname for fk in table.c.asset_id.foreign_keys} == {"assets.id"}
    assert {tuple(index.columns.keys()) for index in table.indexes} == {
        ("asset_id", "kind", "effective_date")
    }


@pytest.mark.parametrize("upgrade", [True, False])
def test_offline_postgres_sql(upgrade: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/offline")
    monkeypatch.setattr("logging.config.fileConfig", Mock())
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    if upgrade:
        command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
        sql = output.getvalue()
        assert "CREATE TABLE knowledge_documents" in sql
        assert "FOREIGN KEY(asset_id) REFERENCES assets (id)" in sql
        assert "UNIQUE (kind, external_id)" in sql
        assert "metadata JSON DEFAULT '{}' NOT NULL" in sql
        assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in sql
        assert "(asset_id, kind, effective_date)" in sql
    else:
        command.downgrade(config, f"{REVISION}:{PREVIOUS}", sql=True)
        sql = output.getvalue()
        assert sql.index("DROP INDEX") < sql.index("DROP TABLE knowledge_documents")


def test_sqlite_upgrade_and_downgrade(monkeypatch: pytest.MonkeyPatch) -> None:
    from alembic.migration import MigrationContext
    from alembic.operations import Operations

    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    revision = script.get_revision(REVISION)
    assert revision is not None
    migration = revision.module
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE assets (id INTEGER PRIMARY KEY)")
            monkeypatch.setattr(
                migration, "op", Operations(MigrationContext.configure(connection))
            )
            migration.upgrade()
            inspector = inspect(connection)
            assert inspector.get_unique_constraints("knowledge_documents")[0][
                "column_names"
            ] == ["kind", "external_id"]
            assert (
                inspector.get_foreign_keys("knowledge_documents")[0]["referred_table"]
                == "assets"
            )
            migration.downgrade()
            assert "knowledge_documents" not in inspect(connection).get_table_names()
    finally:
        engine.dispose()
