"""Ortak test hazırlıkları.

Testler DATABASE_URL ortam değişkeninin gösterdiği, migrasyonu uygulanmış
veritabanında çalışır. Yalnızca sentetik veri kullanılır ve her test sonunda
işlem geri alınır.
"""

import os
from contextlib import contextmanager
from uuid import UUID

import pytest
from fastapi import Header
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text


# Testler gerçek müvekkil anahtarına bağlı kalmasın; yalnızca bu süreçte geçerli sabit bir test anahtarı
os.environ["MUVEKKIL_ANAHTARI"] = "dGVzdC1hbmFodGFyaS0zMi1iYXl0LXVnbnVsZXItMDA"


def ekle(conn, sql, **params):
    return conn.execute(text(sql + " RETURNING id"), params).scalar_one()


@pytest.fixture(scope="session")
def engine():
    url = os.environ.get("DATABASE_URL")
    if not url:
        pytest.skip("DATABASE_URL ortam değişkeni tanımlı değil.")
    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def conn(engine):
    with engine.connect() as c:
        tx = c.begin()
        yield c
        tx.rollback()


@pytest.fixture
def depolama(tmp_path):
    from app.belge.depolama import SifreliDepolama, YerelDepolama

    return SifreliDepolama(YerelDepolama(tmp_path))


def basliktan_kullanici(x_kullanici_id: UUID = Header()) -> UUID:
    """YALNIZCA TEST: kullanıcıyı oturum çerezi yerine X-Kullanici-Id başlığından okur.

    Belge kurallarını sınayan testler her seferinde giriş yapmak zorunda kalmasın diye.
    Gerçek giriş ve oturum akışı tests/test_kimlik.py içinde bu kısayol olmadan sınanır.
    """
    return x_kullanici_id


@pytest.fixture
def istemci(conn, depolama):
    """API istemcisi: istek bağlantısı ve red kaydı için açılan ayrı işlem test bağlantısına yönlenir;
    kullanıcı X-Kullanici-Id başlığından okunur (bkz. basliktan_kullanici).

    Not: bu düzende reddedilen istekte isteğin işlemi geri alınmaz (bağlantı testindir);
    red kaydının geri almadan etkilenmediği tests/test_erisim_reddi.py içinde gerçek
    işlemlerle ayrıca sınanır.
    """
    from app.belge.api import ayri_islem, depolama_al
    from app.db import baglanti
    from app.kimlik.api import gecerli_kullanici
    from app.main import app

    @contextmanager
    def kayit_noktasi():
        with conn.begin_nested():
            yield conn

    app.dependency_overrides[baglanti] = lambda: conn
    app.dependency_overrides[depolama_al] = lambda: depolama
    app.dependency_overrides[ayri_islem] = lambda: kayit_noktasi
    app.dependency_overrides[gecerli_kullanici] = basliktan_kullanici
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def dava(conn):
    """Sentetik büro, avukat, müvekkil ve dava dosyası oluşturur; avukata dosya erişimi verir."""
    buro = ekle(conn, "INSERT INTO buro (ad) VALUES ('Örnek Hukuk Bürosu')")
    kullanici = ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Deneme Kişi', 'deneme@ornek.test', 'avukat')",
        b=buro,
    )
    muvekkil = ekle(
        conn,
        "INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'gercek_kisi', 'Sentetik Müvekkil')",
        b=buro,
    )
    dava_id = ekle(
        conn,
        "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, olusturan_kullanici_id) "
        "VALUES (:b, :m, '2026/1', 'Sentetik Dava', :k)",
        b=buro, m=muvekkil, k=kullanici,
    )
    conn.execute(
        text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'sorumlu')"),
        {"d": dava_id, "k": kullanici},
    )
    return {"buro": buro, "kullanici": kullanici, "dava": dava_id}
