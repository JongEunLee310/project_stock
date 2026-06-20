import ast
import importlib
from pathlib import Path

from app.db.base import Base


REPO_ROOT = Path(__file__).resolve().parents[1]
DOMAIN_ROOT = REPO_ROOT / "app" / "domains"
ALEMBIC_ENV = REPO_ROOT / "alembic" / "env.py"


def _domain_model_modules() -> set[str]:
    return {
        ".".join(model_path.relative_to(REPO_ROOT).with_suffix("").parts)
        for model_path in DOMAIN_ROOT.glob("**/*model.py")
    }


def _alembic_env_imports() -> set[str]:
    parsed = ast.parse(ALEMBIC_ENV.read_text())
    return {
        alias.name
        for node in ast.walk(parsed)
        if isinstance(node, ast.Import)
        for alias in node.names
    }


def test_alembic_env_imports_all_domain_models() -> None:
    assert _domain_model_modules() <= _alembic_env_imports()


def test_domain_models_register_tables_in_base_metadata() -> None:
    for module_name in sorted(_domain_model_modules()):
        module = importlib.import_module(module_name)
        mapped_tables: list[str] = []

        for model in vars(module).values():
            if not isinstance(model, type) or not issubclass(model, Base):
                continue
            if model is Base:
                continue

            table_name = getattr(model, "__tablename__", None)
            if isinstance(table_name, str):
                mapped_tables.append(table_name)

        assert mapped_tables, f"{module_name} has no mapped model classes"
        for table_name in mapped_tables:
            assert table_name in Base.metadata.tables
