from logging.config import fileConfig

from sqlmodel import SQLModel

import app.models  # noqa: F401  (registers tables)
from alembic import context
from app.config import get_settings
from app.db import make_engine

config = context.config
# When the app runs migrations itself (sandbox reset), don't let Alembic's logging config
# disable the app's loggers.
if config.config_file_name is not None and not config.attributes.get("embedded"):
    fileConfig(config.config_file_name)

target_metadata = SQLModel.metadata


def _url() -> str:
    return config.get_main_option("sqlalchemy.url") or get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = make_engine(_url())
    with connectable.connect() as connection:
        # SQLite batch migrations rebuild tables; FK enforcement would block dropping a table
        # other tables reference. Must be set outside a transaction.
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        # Commit the implicit transaction the PRAGMA opened; otherwise Alembic sees an
        # existing transaction, doesn't manage it, and batch operations are silently lost.
        connection.commit()
        context.configure(
            connection=connection, target_metadata=target_metadata, render_as_batch=True
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
