from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

from app.core.config import settings
from app.db.base import Base
import app.domains.assets.model  # noqa: F401 — registers Asset model for autogenerate
import app.domains.jobs.model  # noqa: F401 — registers JobRun model for autogenerate
import app.domains.news.model  # noqa: F401 — registers NewsItem model for autogenerate
import app.domains.raw_news.model  # noqa: F401 — registers RawNewsEvent model for autogenerate
import app.domains.theses.model  # noqa: F401 — registers InvestmentThesis model for autogenerate
import app.domains.users.model  # noqa: F401 — registers User model for autogenerate
import app.domains.watchlists.model  # noqa: F401 — registers Watchlist models for autogenerate

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
