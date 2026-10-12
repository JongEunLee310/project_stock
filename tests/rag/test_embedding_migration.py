from io import StringIO
from pathlib import Path
import re
from unittest.mock import Mock

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from pgvector.sqlalchemy import Vector
import pytest

from app.core.config import settings
from app.domains.rag.model import DocumentChunk
from app.domains.rag.types import EMBEDDING_DIMENSIONS

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "c3d4e5f60070"
PREVIOUS_REVISION = "c3d4e5f6006f"


def test_embedding_migration_head_and_model_dimension() -> None:
    config = Config(str(REPO_ROOT / "alembic.ini"))
    script = ScriptDirectory.from_config(config)
    assert script.get_heads() == [REVISION]
    revision = script.get_revision(REVISION)
    assert revision is not None
    assert revision.down_revision == PREVIOUS_REVISION
    column_type = DocumentChunk.__table__.c.embedding.type
    assert isinstance(column_type, Vector)
    assert column_type.dim == EMBEDDING_DIMENSIONS == 1024


@pytest.mark.parametrize("upgrade", [True, False])
def test_embedding_migration_sql_order(
    upgrade: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://localhost/offline")
    # SQL 생성이 pytest의 logging 설정을 덮어쓰지 않게 한다.
    monkeypatch.setattr("logging.config.fileConfig", Mock())
    output = StringIO()
    config = Config(str(REPO_ROOT / "alembic.ini"), output_buffer=output)
    if upgrade:
        command.upgrade(config, f"{PREVIOUS_REVISION}:{REVISION}", sql=True)
        dimensions = EMBEDDING_DIMENSIONS
    else:
        command.downgrade(config, f"{REVISION}:{PREVIOUS_REVISION}", sql=True)
        previous_output = StringIO()
        previous_config = Config(
            str(REPO_ROOT / "alembic.ini"), output_buffer=previous_output
        )
        script = ScriptDirectory.from_config(previous_config)
        previous_revision = script.get_revision(PREVIOUS_REVISION)
        assert previous_revision is not None
        command.upgrade(
            previous_config,
            f"{previous_revision.down_revision}:{PREVIOUS_REVISION}",
            sql=True,
        )
        previous_dimension = re.search(
            r"embedding VECTOR\((\d+)\)", previous_output.getvalue()
        )
        assert previous_dimension is not None
        dimensions = int(previous_dimension.group(1))
    sql = output.getvalue()
    statements = [
        "DROP INDEX ix_document_chunks_embedding;",
        "DELETE FROM document_chunks;",
        f"ALTER TABLE document_chunks ALTER COLUMN embedding TYPE VECTOR({dimensions});",
        "CREATE INDEX ix_document_chunks_embedding ON document_chunks "
        "USING hnsw (embedding vector_cosine_ops);",
    ]
    positions = [sql.index(statement) for statement in statements]
    assert positions == sorted(positions)
