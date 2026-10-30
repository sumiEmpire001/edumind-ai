from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.database.base import Base

url = get_settings().database_url.get_secret_value()


def run_migrations_offline():
    context.configure(
        url=url,
        target_metadata=Base.metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    engine = create_engine(
        url, poolclass=pool.NullPool, hide_parameters=True, connect_args={"connect_timeout": 5}
    )
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=Base.metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
