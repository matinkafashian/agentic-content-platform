from logging.config import fileConfig
from os import environ
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.admin import models as admin_models  # noqa: F401
from app.brand import models as brand_models  # noqa: F401
from app.catalog import models  # noqa: F401
from app.content import models as content_models  # noqa: F401
from app.core.database import Base
from app.media import models as media_models  # noqa: F401
from app.publishing import models as publishing_models  # noqa: F401
from app.support import models as support_models  # noqa: F401

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

if database_url := environ.get("DATABASE_URL"):
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))

target_metadata = Base.metadata


def ensure_sqlite_parent(url: str) -> None:
    prefix = "sqlite:///"
    if url.startswith(prefix) and not url.startswith("sqlite:////"):
        database_path = Path(url.removeprefix(prefix))
        if database_path.parent != Path("."):
            database_path.parent.mkdir(parents=True, exist_ok=True)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    ensure_sqlite_parent(section["sqlalchemy.url"])
    connectable = engine_from_config(
        section,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
