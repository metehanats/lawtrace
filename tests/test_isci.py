"""Metin çıkarma işçisi testleri. Tüm belgeler sentetiktir."""

import threading
from contextlib import contextmanager

import pytest
from sqlalchemy import text

from app.belge import isci, metin_cikarma
from app.belge.depolama import YerelDepolama
from app.belge.yukleme import belge_yukle
from test_belge import pdf_uret


@pytest.fixture
def depolama(tmp_path):
    return YerelDepolama(tmp_path)


@pytest.fixture
def islem_ac(conn):
    """Her görev turunu test işlemi içinde bir kayıt noktasıyla (savepoint) açar."""
    @contextmanager
    def ac():
        with conn.begin_nested():
            yield conn
    return ac


def _yukle(conn, dava, depolama, veri):
    return belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                       orijinal_ad="belge.pdf", veri=veri)


def _bekleyen_sayisi(conn):
    return conn.execute(text(
        "SELECT count(*) FROM isleme_gorevi WHERE adim = 'metin_cikarma' AND durum = 'bekliyor'"
    )).scalar_one()


def _durumlar(conn, sonuclar):
    return [
        conn.execute(text("SELECT durum FROM belge WHERE id = :b"), {"b": s["id"]}).scalar_one()
        for s in sonuclar
    ]


def test_tum_bekleyen_gorevler_islenir(conn, dava, depolama, islem_ac):
    onceki = _bekleyen_sayisi(conn)
    sonuclar = [_yukle(conn, dava, depolama, pdf_uret(f"Sentetik belge {i}")) for i in range(3)]
    assert isci.bekleyenleri_isle(islem_ac, depolama) == onceki + 3
    assert _durumlar(conn, sonuclar) == ["hazir"] * 3
    assert _bekleyen_sayisi(conn) == 0


def test_hatali_belge_digerlerini_durdurmaz(conn, dava, depolama, islem_ac):
    sonuclar = [
        _yukle(conn, dava, depolama, pdf_uret("Saglam belge 1")),
        _yukle(conn, dava, depolama, b"%PDF-1.4\nbozuk icerik"),
        _yukle(conn, dava, depolama, pdf_uret("Saglam belge 2")),
    ]
    isci.bekleyenleri_isle(islem_ac, depolama)
    assert sorted(_durumlar(conn, sonuclar)) == ["hata", "hazir", "hazir"]


def test_durma_istegi_varsa_gorev_alinmaz(conn, dava, depolama, islem_ac):
    sonuc = _yukle(conn, dava, depolama, pdf_uret("Bekleyecek belge"))
    dur = threading.Event()
    dur.set()
    assert isci.bekleyenleri_isle(islem_ac, depolama, dur) == 0
    assert _durumlar(conn, [sonuc]) == ["yuklendi"]


def test_gorev_ortasinda_kesilirse_gorev_bekliyor_kalir(conn, dava, depolama, islem_ac, monkeypatch):
    sonuc = _yukle(conn, dava, depolama, pdf_uret("Kesintiye ugrayacak belge"))

    def kes(*_):
        # İşçinin görev ortasında durdurulmasını (Ctrl+C) taklit eder
        raise KeyboardInterrupt

    monkeypatch.setattr(metin_cikarma, "sayfalari_cikar", kes)
    with pytest.raises(KeyboardInterrupt):
        isci.bekleyenleri_isle(islem_ac, depolama)

    gorev = conn.execute(
        text("SELECT durum, tekrar_sayisi FROM isleme_gorevi WHERE id = :g"),
        {"g": sonuc["metin_cikarma_gorevi_id"]},
    ).one()
    assert tuple(gorev) == ("bekliyor", 0)
    assert _durumlar(conn, [sonuc]) == ["yuklendi"]

    # Sonraki turda görev normal şekilde işlenir
    monkeypatch.undo()
    isci.bekleyenleri_isle(islem_ac, depolama)
    assert _durumlar(conn, [sonuc]) == ["hazir"]


def test_calistir_hata_sonrasi_kapanmaz(depolama):
    cagri = []
    dur = threading.Event()

    @contextmanager
    def bozuk_islem():
        cagri.append(1)
        if len(cagri) >= 2:
            dur.set()
        raise RuntimeError("bağlantı koptu")
        yield  # pragma: no cover

    isci.calistir(bozuk_islem, depolama, dur, bekleme_saniye=0)
    assert len(cagri) == 2
