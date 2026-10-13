import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    "module_name",
    [
        "scripts.run_daily_research",
        "scripts.run_filing_analysis",
        "scripts.backfill_rag_embeddings",
        "scripts.evaluate_rag_retrieval",
    ],
)
def test_script_import_registers_all_foreign_key_targets(module_name: str) -> None:
    script = textwrap.dedent(
        """
        import importlib
        import sys

        importlib.import_module(sys.argv[1])
        from app.db.base import Base

        assert "alerts" in Base.metadata.tables
        assert "users" in Base.metadata.tables
        user_fk, = Base.metadata.tables["alerts"].c.user_id.foreign_keys
        assert user_fk.column is Base.metadata.tables["users"].c.id

        for table in Base.metadata.tables.values():
            for foreign_key in table.foreign_keys:
                try:
                    foreign_key.column
                except Exception as exc:
                    raise AssertionError(
                        f"{table.name}.{foreign_key.parent.name}"
                        f" -> {foreign_key.target_fullname}"
                    ) from exc
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script, module_name],
        capture_output=True,
        check=False,
        cwd=Path(__file__).resolve().parent.parent,
        env={**os.environ, "DATABASE_URL": "sqlite://"},
        text=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stdout + result.stderr
