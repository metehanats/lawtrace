"""Veritabanı bağlantısı."""

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine

from app import ayarlar


@lru_cache
def engine() -> Engine:
    return create_engine(ayarlar.veritabani_url())


def baglanti() -> Iterator[Connection]:
    """İstek başına bir işlem açar; hata olursa geri alır, yoksa onaylar."""
    with engine().begin() as conn:
        yield conn
