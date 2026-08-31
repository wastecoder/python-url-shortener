"""How Alembic finds this project's database and its models.

Two things are wired here that the generated file leaves blank.

**The DSN comes from `Settings`, not from `alembic.ini`.** A connection string in a versioned `.ini`
is a second source of truth for the one value that decides which database gets migrated, and the
copy in the file is the one nobody updates. `alembic.ini` therefore carries no `sqlalchemy.url` at
all, and this module reads the same setting the application reads.

**`sqlalchemy.url` is still honoured when something sets it programmatically**, and that is the
hook Fase 5 needs: the Testcontainers fixture starts a PostgreSQL on a random port and runs these
same migrations against it, which it does by setting the option on a `Config` object in memory.
That path never touches the file.
"""

from logging.config import fileConfig

import sqlalchemy as sa
from alembic import context

from url_shortener.adapter.config.settings import get_settings
from url_shortener.adapter.persistence.entity import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importing the `entity` package is what puts both tables in here; the package re-exports them for
# exactly this reason. An entity that no import reaches is a table `--autogenerate` proposes to
# drop.
target_metadata = Base.metadata


def database_url() -> str:
    """The database to migrate: whatever was injected, otherwise the application's own setting."""
    injected = config.get_main_option("sqlalchemy.url")
    return injected or get_settings().database_url


def run_migrations_offline() -> None:
    """Emit the SQL to stdout instead of running it, with no database and no driver involved.

    Kept because `alembic upgrade head --sql` is how the statements get reviewed before they touch
    anything that matters, which is the whole argument for migrations over `create_all()`.
    """
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Connect and run the migrations for real.

    `NullPool` because this process opens one connection, runs to the end and exits; a pool would
    only be a set of idle connections nobody closes.
    """
    connectable = sa.create_engine(database_url(), poolclass=sa.pool.NullPool)

    try:
        with connectable.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)

            with context.begin_transaction():
                context.run_migrations()
    finally:
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
