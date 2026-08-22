"""Alembic environment for the research tables.

Two apps share one database, so two things must hold:

* Revisions are tracked in ``alembic_version_research``. The archiver owns the
  default ``alembic_version`` table and runs ``alembic upgrade head`` before
  every scheduled ingest — sharing one pointer would make each app try to
  re-run the other's history.
* Autogenerate considers only tables in this app's metadata. Without the
  ``include_object`` filter below, every autogenerate would propose dropping
  the archiver's 21 tables.
"""

from __future__ import annotations

from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import get_settings
from app.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

VERSION_TABLE = "alembic_version_research"


def _sync_url() -> str:
    """Alembic runs sync; normalize whatever driver the URL carries."""
    url = get_settings().database_url
    scheme, sep, rest = url.partition("://")
    if sep and scheme in ("postgres", "postgresql", "postgresql+asyncpg"):
        return "postgresql+psycopg://" + rest
    return url


def include_object(
    obj: Any, name: str | None, type_: str, reflected: bool, compare_to: Any
) -> bool:
    """Restrict autogenerate to objects this app owns.

    Two exclusions:

    * Tables outside this app's metadata — otherwise every autogenerate
      proposes dropping the archiver's tables.
    * Indexes that exist in the database but in no model. TimescaleDB creates
      its own index on a hypertable's time column (``prices_date_idx``), and
      autogenerate reads its absence from the metadata as a deletion.
    """
    if type_ == "table":
        return name in target_metadata.tables
    if type_ == "index" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline() -> None:
    context.configure(
        url=_sync_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        version_table=VERSION_TABLE,
        include_object=include_object,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _sync_url()
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table=VERSION_TABLE,
            include_object=include_object,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
