import os

# Import our models and database configuration
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

# Import all models to ensure they're registered with Base.metadata
import models  # noqa: E402, F401
import project_models  # noqa: E402, F401
from database import DATABASE_URL, Base  # noqa: E402

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Use the DATABASE_URL from our database configuration
# This will automatically use SQLite for local dev and PostgreSQL for production
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
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

    # Add SQLite specific configuration
    if "sqlite" in url:
        configuration["sqlalchemy.connect_args"] = {"check_same_thread": False}

    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite specific options for batch operations
            render_as_batch=True if "sqlite" in url else False,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
