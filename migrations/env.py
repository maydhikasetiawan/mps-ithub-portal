from logging.config import fileConfig
import os
import sys

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = None

def get_db_url():
    host = os.getenv('DB_HOST', 'postgres-server')
    name = os.getenv('DB_NAME', 'db_monitoring')
    user = os.getenv('DB_USER', 'admin_server')
    password = os.getenv('DB_PASS', 'PasswordSuperAman123')
    port = os.getenv('DB_PORT', '5432')
    return f"postgresql://{user}:{password}@{host}:{port}/{name}"

def run_migrations_offline() -> None:
    url = get_db_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online() -> None:
    from sqlalchemy import create_engine

    connectable = create_engine(get_db_url())

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata
        )

        with context.begin_transaction():
            context.run_migrations()

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()