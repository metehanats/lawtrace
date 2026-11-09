"""Veritabanı şeması testleri."""

import hashlib
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from conftest import ekle as _ekle

PROJE = Path(__file__).resolve().parents[1]

BEKLENEN_TABLOLAR = {
    "buro", "kullanici", "muvekkil", "dava_dosyasi", "dosya_erisim",
    "belge", "belge_sayfa", "isleme_gorevi", "analiz_calistirmasi",
    "bulgu", "kaynak_alinti", "bulgu_inceleme", "uyusmazlik",
    "olay", "iddia", "delil_baglantisi", "denetim_kaydi",
}


def _belge_ekle(conn, dava, icerik=b"sentetik belge"):
    return _ekle(
        conn,
        "INSERT INTO belge (buro_id, dava_dosyasi_id, orijinal_ad, mime_tur, depolama_anahtari, "
        "sha256_ozet, yukleyen_kullanici_id) "
        "VALUES (:b, :d, 'dilekce.pdf', 'application/pdf', :anahtar, :ozet, :k)",
        b=dava["buro"], d=dava["dava"], k=dava["kullanici"],
        anahtar=f"test/{hashlib.md5(icerik).hexdigest()}",
        ozet=hashlib.sha256(icerik).hexdigest(),
    )


def test_tum_tablolar_var(conn):
    tablolar = set(conn.execute(text(
        "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
    )).scalars())
    assert BEKLENEN_TABLOLAR <= tablolar


def test_veritabani_son_migrasyonda(conn):
    yapilandirma = Config(str(PROJE / "db" / "alembic.ini"))
    son = ScriptDirectory.from_config(yapilandirma).get_current_head()
    assert conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one() == son


def _sema_ozeti(conn, sema: str):
    def sade(deger: str) -> str:
        # Başka şemadaki nesneler adlarında şema önekiyle görünür; karşılaştırma için atılır
        return deger.replace("public.", "").replace(f"{sema}.", "")

    sutunlar = conn.execute(text(
        "SELECT table_name, column_name, data_type, is_nullable, coalesce(column_default, '') "
        "FROM information_schema.columns WHERE table_schema = :s AND table_name <> 'alembic_version'"
    ), {"s": sema}).all()
    kisitlar = conn.execute(text(
        "SELECT conrelid::regclass::text, conname, pg_get_constraintdef(oid) FROM pg_constraint "
        "WHERE connamespace = CAST(:s AS regnamespace) AND conrelid::regclass::text NOT LIKE '%alembic_version'"
    ), {"s": sema}).all()
    indeksler = conn.execute(text(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname = :s AND tablename <> 'alembic_version'"
    ), {"s": sema}).all()
    return (
        {tuple(sade(str(x)) for x in s) for s in sutunlar},
        {tuple(sade(str(x)) for x in k) for k in kisitlar},
        {tuple(sade(str(x)) for x in i) for i in indeksler},
    )


def test_schema_sql_migrasyonlarla_ayni(conn):
    """db/schema.sql (başvuru belgesi) ile migrasyonların ürettiği şema birebir aynı olmalı.

    Yeni bir migrasyon eklenip schema.sql güncellenmeyi unutulursa bu test başarısız olur.
    """
    conn.execute(text("CREATE SCHEMA sema_karsilastirma"))
    conn.execute(text("SET LOCAL search_path TO sema_karsilastirma"))
    conn.exec_driver_sql((PROJE / "db" / "schema.sql").read_text(encoding="utf-8"))
    beklenen = _sema_ozeti(conn, "public")
    bulunan = _sema_ozeti(conn, "sema_karsilastirma")
    for ad, b, g in zip(["sütun", "kısıt", "indeks"], beklenen, bulunan):
        assert b == g, (ad, sorted(b ^ g)[:5])


def test_bulgu_varsayilan_olarak_otomatik(conn, dava):
    analiz = _ekle(
        conn,
        "INSERT INTO analiz_calistirmasi (buro_id, dava_dosyasi_id, kapsam, model_saglayici, "
        "model_adi, prompt_surumu, calistiran_kullanici_id) "
        "VALUES (:b, :d, 'coklu_belge', 'deneme', 'deneme-model', 'v0', :k)",
        b=dava["buro"], d=dava["dava"], k=dava["kullanici"],
    )
    bulgu = _ekle(
        conn,
        "INSERT INTO bulgu (analiz_calistirmasi_id, dava_dosyasi_id, tur, ozet, guven_seviyesi) "
        "VALUES (:a, :d, 'tarih', 'Sözleşme tarihi', 'orta')",
        a=analiz, d=dava["dava"],
    )
    durum = conn.execute(
        text("SELECT dogrulama_durumu FROM bulgu WHERE id = :i"), {"i": bulgu}
    ).scalar_one()
    assert durum == "otomatik"


def test_ayni_belge_iki_kez_yuklenemez(conn, dava):
    _belge_ekle(conn, dava)
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _ekle(
                conn,
                "INSERT INTO belge (buro_id, dava_dosyasi_id, orijinal_ad, mime_tur, depolama_anahtari, "
                "sha256_ozet, yukleyen_kullanici_id) "
                "VALUES (:b, :d, 'kopya.pdf', 'application/pdf', 'test/baska-anahtar', :ozet, :k)",
                b=dava["buro"], d=dava["dava"], k=dava["kullanici"],
                ozet=hashlib.sha256(b"sentetik belge").hexdigest(),
            )


def test_desteklenmeyen_dosya_turu_reddedilir(conn, dava):
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _ekle(
                conn,
                "INSERT INTO belge (buro_id, dava_dosyasi_id, orijinal_ad, mime_tur, depolama_anahtari, "
                "sha256_ozet, yukleyen_kullanici_id) "
                "VALUES (:b, :d, 'resim.png', 'image/png', 'test/png', :ozet, :k)",
                b=dava["buro"], d=dava["dava"], k=dava["kullanici"],
                ozet=hashlib.sha256(b"png").hexdigest(),
            )


def test_uyusmazlik_ayni_bulguyu_iki_kez_gosteremez(conn, dava):
    analiz = _ekle(
        conn,
        "INSERT INTO analiz_calistirmasi (buro_id, dava_dosyasi_id, kapsam, model_saglayici, "
        "model_adi, prompt_surumu, calistiran_kullanici_id) "
        "VALUES (:b, :d, 'coklu_belge', 'deneme', 'deneme-model', 'v0', :k)",
        b=dava["buro"], d=dava["dava"], k=dava["kullanici"],
    )
    bulgu = _ekle(
        conn,
        "INSERT INTO bulgu (analiz_calistirmasi_id, dava_dosyasi_id, tur, ozet, guven_seviyesi) "
        "VALUES (:a, :d, 'tutar', '10.000 TL', 'yuksek')",
        a=analiz, d=dava["dava"],
    )
    with pytest.raises(IntegrityError):
        with conn.begin_nested():
            _ekle(
                conn,
                "INSERT INTO uyusmazlik (dava_dosyasi_id, tur, ilgili_bulgu_1_id, ilgili_bulgu_2_id, "
                "aciklama, ciddiyet) VALUES (:d, 'tutar', :x, :x, 'aynı bulgu', 'dusuk')",
                d=dava["dava"], x=bulgu,
            )
