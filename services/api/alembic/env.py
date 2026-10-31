import logging
import os

# Import our models and database configuration
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# /shared is where models.py, project_models.py, and report_models.py
# now live (consolidated 2026-05-19, commits f481c79 + a4c8a8c).
# Alembic doesn't share sys.path with the API's runtime, so we have to
# add it here. Falls back to the relative `services/shared/` path for
# host-local alembic runs where /shared isn't a real Docker mount.
_shared_dir = (
    "/shared"
    if os.path.exists("/shared")
    else os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "shared")
    )
)
if _shared_dir not in sys.path:
    sys.path.insert(0, _shared_dir)

# Import all models to ensure they're registered with Base.metadata
import models  # noqa: E402, F401
import project_models  # noqa: E402, F401
import report_models  # noqa: E402, F401  — ProjectReport on Base; without this `alembic check` would propose `remove_table('project_reports')` because the metadata snapshot was incomplete.
from database import DATABASE_URL, Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use the DATABASE_URL from our database configuration
# This will automatically use SQLite for local dev and PostgreSQL for production
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging — but ONLY when logging is
# not configured yet (standalone `alembic ...` CLI runs). The API runs
# migrations IN-PROCESS at startup (main.py lifespan -> command.upgrade),
# and fileConfig's default disable_existing_loggers=True permanently
# muted every already-imported logger in every uvicorn worker — routers,
# mailer, even uvicorn.access: prod pods logged nothing after startup.
# (alembic.ini's [logger_root] would also re-level root to WARN, so
# passing disable_existing_loggers=False alone would still eat INFO.)
if config.config_file_name is not None and not logging.getLogger().handlers:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # SQLite specific options
        render_as_batch=True if "sqlite" in url else False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Get the database URL
    url = config.get_main_option("sqlalchemy.url")

    # Configure engine based on database type
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = url

    connect_args = {}
    # Add SQLite specific configuration
    if "sqlite" in url:
        connect_args = {"check_same_thread": False}
    elif url.startswith("postgresql"):
        # Lets pg_stat_activity tell a migration apart from the API lanes
        # ("benger-api" / "benger-api-async") and the workers.
        connect_args = {"application_name": "benger-migrations"}

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
        connect_args=connect_args,
    )

    def _upgrade_once() -> None:
        with connectable.connect() as connection:
            context.configure(
                connection=connection,
                target_metadata=target_metadata,
                # SQLite specific options for batch operations
                render_as_batch=True if "sqlite" in url else False,
            )

            with context.begin_transaction():
                context.run_migrations()

    # Migrations on hot tables set a 5 s lock_timeout. A transaction that
    # holds the table for a little longer (an idle worker session) must not
    # fail the deploy, so a lock timeout or deadlock is retried a few times
    # (6 attempts, 20 s apart by default; see utils/migration_lock_retry.py).
    # Each attempt is its own transaction, so a failed one leaves the schema
    # at the last committed revision. The API lifespan's advisory lock is
    # held by its caller for the whole retry window, so concurrent API
    # processes keep waiting on it as before.
    from utils.migration_lock_retry import describe_lock_holders, run_with_lock_retry

    run_with_lock_retry(
        _upgrade_once,
        describe_holders=lambda: describe_lock_holders(connectable),
    )


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
