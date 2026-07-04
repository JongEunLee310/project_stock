import os
import subprocess
import sys
import textwrap


def test_worker_job_import_registers_all_foreign_key_targets() -> None:
    script = textwrap.dedent(
        """
        import app.worker.jobs.llm_analysis
        from app.db.base import Base

        missing = []
        for table_name, table in sorted(Base.metadata.tables.items()):
            for foreign_key in table.foreign_keys:
                target_table_name = foreign_key.target_fullname.rsplit(".", 1)[0]
                if target_table_name not in Base.metadata.tables:
                    missing.append(
                        f"{table_name}.{foreign_key.parent.name}"
                        f" -> {foreign_key.target_fullname}"
                    )

        print("\\n".join(missing))
        raise SystemExit(1 if missing else 0)
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        check=False,
        env=os.environ.copy(),
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
