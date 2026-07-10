import importlib.util
from pathlib import Path
from typing import Any, cast

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import create_engine, inspect


def test_signal_key_points_migration_upgrade_downgrade_round_trip() -> None:
    migration_path = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "c3d4e5f60062_add_signal_key_points.py"
    )
    spec = importlib.util.spec_from_file_location(
        "c3d4e5f60062_add_signal_key_points",
        migration_path,
    )
    assert spec is not None
    assert spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    metadata = sa.MetaData()
    sa.Table(
        "signals",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    metadata.create_all(engine)

    with engine.begin() as connection:
        context = MigrationContext.configure(connection)
        operations = Operations(context)
        original_op = cast(Any, migration).op
        cast(Any, migration).op = operations
        try:
            cast(Any, migration).upgrade()
            assert "key_points" in {
                column["name"] for column in inspect(connection).get_columns("signals")
            }

            cast(Any, migration).downgrade()
            assert "key_points" not in {
                column["name"] for column in inspect(connection).get_columns("signals")
            }
        finally:
            cast(Any, migration).op = original_op
