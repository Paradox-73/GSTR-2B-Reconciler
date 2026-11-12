from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

from api import tables  # noqa: F401  (registers the tables on Base.metadata)
from api.db import Base
from api.settings import env

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

URL = env("DATABASE_URL", "sqlite:///./dev.db")  # not get_settings(): no JWT needed to migrate


def run_migrations_offline() -> None:
    context.configure(url=URL, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    with create_engine(URL).connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata,
                          render_as_batch=connection.dialect.name == "sqlite")
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
