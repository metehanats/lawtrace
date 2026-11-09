"""Alembic ortam yapılandırması.

Bağlantı adresi DATABASE_URL ortam değişkeninden okunur. Adres koda veya
ini dosyasına yazılmaz.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model tabanlı otomatik üretim kullanılmadığı için metadata verilmez.
# Şema, SQL dosyası üzerinden 0001 migrasyonuyla yönetilir.
target_metadata = None


def get_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL ortam değişkeni tanımlı değil.")
    return url


def run_migrations_offline() -> None:
    context.configure(url=get_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_url())
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
