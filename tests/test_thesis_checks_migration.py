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

from app.core.config import settings

ROOT = Path(__file__).resolve().parents[1]
REVISION = "c3d4e5f60074"
PREVIOUS = "c3d4e5f60073"


def test_single_head() -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None and revision.down_revision == PREVIOUS


@pytest.mark.parametrize("upgrade", [True, False])
def test_postgres_offline_sql(upgrade: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/offline")
    monkeypatch.setattr("logging.config.fileConfig", Mock())
    output = StringIO()
    config = Config(str(ROOT / "alembic.ini"), output_buffer=output)
    if upgrade:
        command.upgrade(config, f"{PREVIOUS}:{REVISION}", sql=True)
        sql = output.getvalue()
        assert "CREATE TABLE thesis_checks" in sql
        for table, column in [
            ("users", "user_id"),
            ("decision_logs", "decision_id"),
            ("assets", "asset_id"),
        ]:
            assert f"FOREIGN KEY({column}) REFERENCES {table} (id)" in sql
        assert "UNIQUE (decision_id, check_date)" in sql
        assert "created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL" in sql
        assert "(user_id, check_date)" in sql
        assert "ADD COLUMN source VARCHAR(20) DEFAULT 'RULE' NOT NULL" in sql
        assert "ALTER COLUMN rule_id DROP NOT NULL" in sql
    else:
        command.downgrade(config, f"{REVISION}:{PREVIOUS}", sql=True)
        sql = output.getvalue()
        assert sql.index("DELETE FROM alert_deliveries") < sql.index(
            "DELETE FROM alert_events"
        )
        assert sql.index("DELETE FROM alert_events") < sql.index(
            "ALTER COLUMN rule_id SET NOT NULL"
        )
        assert "DROP COLUMN source" in sql
        assert "DROP TABLE thesis_checks" in sql


def test_sqlite_roundtrip_preserves_rule_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    script = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini")))
    initial = script.get_revision("c3d4e5f60069")
    revision = script.get_revision(REVISION)
    assert initial is not None and revision is not None
    engine = create_engine("sqlite://")
    try:
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            for table in ("users", "assets", "decision_logs"):
                connection.exec_driver_sql(
                    f"CREATE TABLE {table} (id INTEGER PRIMARY KEY)"
                )
                connection.exec_driver_sql(f"INSERT INTO {table} (id) VALUES (1)")
            monkeypatch.setattr(initial.module, "op", operations)
            initial.module.upgrade()
            connection.exec_driver_sql(
                "INSERT INTO alert_rules (id,user_id,name,source,target_type,condition,severity,channels,"
                "cooldown_seconds,delivery_policy) VALUES (1,1,'rule','USER','SYMBOL','{}','HIGH','[]',0,'ONCE_PER_TRANSITION')"
            )
            connection.exec_driver_sql(
                "INSERT INTO alert_events (id,rule_id,user_id,target_type,title,message,severity,triggered_value,evidence,dedup_key) "
                "VALUES (1,1,1,'SYMBOL','rule title','message','HIGH','{}','[]','rule-key')"
            )
            connection.exec_driver_sql(
                "INSERT INTO alert_deliveries (id,alert_event_id,channel,status) VALUES (1,1,'APP','SUCCESS')"
            )
            monkeypatch.setattr(revision.module, "op", operations)
            revision.module.upgrade()
            columns = {
                c["name"]: c for c in inspect(connection).get_columns("alert_events")
            }
            assert columns["rule_id"]["nullable"]
            assert (
                not columns["source"]["nullable"]
                and columns["source"]["default"] == "'RULE'"
            )
            assert connection.exec_driver_sql(
                "SELECT rule_id,source,title,dedup_key FROM alert_events"
            ).one() == (1, "RULE", "rule title", "rule-key")
            inspector = inspect(connection)
            assert inspector.get_unique_constraints("thesis_checks")[0][
                "column_names"
            ] == ["decision_id", "check_date"]
            assert inspector.get_indexes("thesis_checks")[0]["column_names"] == [
                "user_id",
                "check_date",
            ]
            assert {
                fk["referred_table"]
                for fk in inspector.get_foreign_keys("thesis_checks")
            } == {"users", "assets", "decision_logs"}
            connection.exec_driver_sql(
                "INSERT INTO thesis_checks (user_id,decision_id,asset_id,check_date,verdict,content) "
                "VALUES (1,1,1,'2026-10-13','MIXED','{}')"
            )
            connection.exec_driver_sql(
                "INSERT INTO alert_events (id,rule_id,source,user_id,target_type,title,message,severity,triggered_value,evidence,dedup_key) "
                "VALUES (2,NULL,'AGENT',1,'SYMBOL','agent title','message','HIGH','{}','[]','agent-key')"
            )
            connection.exec_driver_sql(
                "INSERT INTO alert_deliveries (id,alert_event_id,channel,status) VALUES (2,2,'APP','SUCCESS')"
            )
            revision.module.downgrade()
            assert "thesis_checks" not in inspect(connection).get_table_names()
            columns = {
                c["name"]: c for c in inspect(connection).get_columns("alert_events")
            }
            assert not columns["rule_id"]["nullable"] and "source" not in columns
            assert [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "SELECT id,rule_id,title FROM alert_events"
                )
            ] == [(1, 1, "rule title")]
            assert [
                tuple(row)
                for row in connection.exec_driver_sql(
                    "SELECT id,alert_event_id FROM alert_deliveries"
                )
            ] == [(1, 1)]
            assert {
                i["name"] for i in inspect(connection).get_indexes("alert_events")
            } == {
                "ix_alert_events_asset_id",
                "ix_alert_events_dedup_key",
                "ix_alert_events_rule_id",
                "ix_alert_events_triggered_at",
                "ix_alert_events_user_id",
            }
            revision.module.upgrade()
            assert (
                connection.exec_driver_sql(
                    "SELECT source FROM alert_events"
                ).scalar_one()
                == "RULE"
            )
    finally:
        engine.dispose()
