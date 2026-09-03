from logging.config import fileConfig

from sqlalchemy import create_engine
from sqlalchemy import pool

from alembic import context

from app.core.config import settings
from app.db.database import Base
from app.models.service import Service


# Alembic Config object
config = context.config


# Configure Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


# Import all models here so Alembic can detect them
# during autogenerate.
#
# Even if Service is not directly referenced below,
# importing it ensures the model is registered with
# Base.metadata.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Run migrations in offline mode.

    In offline mode, Alembic generates SQL without
    establishing a database connection.
    """

    url = settings.database_url

    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={
            "paramstyle": "named",
        },
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Run migrations in online mode.

    Creates a database engine and runs migrations
    against the connected database.
    """

    connectable = create_engine(
        settings.database_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
