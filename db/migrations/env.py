"""Minimal Alembic env - use only if M1 did not create one. URL from DATABASE_URL."""
import os
from logging.config import fileConfig
from alembic import context
from sqlalchemy import engine_from_config, pool

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

def run_online():
    engine = engine_from_config(config.get_section(config.config_ini_section),
                                prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as conn:
        context.configure(connection=conn, target_metadata=None)
        with context.begin_transaction():
            context.run_migrations()

run_online()
