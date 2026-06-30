"""Alembic migration environment (async, psycopg3).

The database URL is read from application settings (``ARC_EVAL_DATABASE_URL``)
rather than alembic.ini, so migrations and the app always agree on the target.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from arc_eval_service.core.config import get_settings

# Import the row-defining storage slices for their side effect: registering each
# table on ``Base.metadata`` so autogenerate and ``--sql`` mode see every table.
from arc_eval_service.storage import evaluation as _evaluation_storage  # noqa: F401
from arc_eval_service.storage import spans as _spans_storage  # noqa: F401
from arc_eval_service.storage.orm import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    settings = get_settings()
    if not settings.database_url:
        msg = "ARC_EVAL_DATABASE_URL must be set to run migrations"
        raise RuntimeError(msg)
    return settings.database_url


def run_migrations_offline() -> None:
    """Emit SQL to stdout without a live connection ('--sql' mode)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Run migrations against a live database using an async engine."""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _database_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(_do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
