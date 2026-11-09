"""Metin çıkarma görevlerinin yeniden deneme politikası testleri. Tüm belgeler sentetiktir."""

import pytest
from sqlalchemy import text

from app import ayarlar
from app.belge.depolama import YerelDepolama
from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle
from test_belge import pdf_uret


class AksayanDepolama(YerelDepolama):
    """İlk `hata_sayisi` okumada geçici hata veren depolama (ör. ağ kesintisi)."""

    def __init__(self, kok, hata_sayisi):
        super().__init__(kok)
        self.kalan_hata = hata_sayisi

    def oku(self, anahtar):
        if self.kalan_hata > 0:
            self.kalan_hata -= 1
            raise OSError("depolamaya ulaşılamadı")
        return super().oku(anahtar)


@pytest.fixture(autouse=True)
def politika(monkeypatch):
    monkeypatch.setattr(ayarlar, "MAKS_DENEME", 3)
    monkeypatch.setattr(ayarlar, "YENIDEN_DENEME_TABAN_SANIYE", 60)


def _yukle(conn, dava, depolama):
    return belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                       orijinal_ad="belge.pdf", veri=pdf_uret("Sentetik belge"))


def _gorev(conn, gorev_id):
    return conn.execute(
        text("SELECT durum, tekrar_sayisi, hata_mesaji FROM isleme_gorevi WHERE id = :g"),
        {"g": gorev_id},
    ).one()


def _belge_durumu(conn, belge_id):
    return conn.execute(text("SELECT durum FROM belge WHERE id = :b"), {"b": belge_id}).scalar_one()


def _geri_al(conn, gorev_id, saniye):
    """Son denemenin bitişini geçmişe çeker; bekleme süresinin dolmasını taklit eder."""
    conn.execute(
        text("UPDATE isleme_gorevi SET bitis = now() - make_interval(secs => :s) WHERE id = :g"),
        {"g": gorev_id, "s": saniye},
    )


def test_gecici_hatada_gorev_yeniden_bekler(conn, dava, tmp_path):
    depolama = AksayanDepolama(tmp_path, hata_sayisi=1)
    sonuc = _yukle(conn, dava, depolama)
    gorev_id = sonuc["metin_cikarma_gorevi_id"]

    assert gorevi_isle(conn, depolama) == gorev_id
    gorev = _gorev(conn, gorev_id)
    assert (gorev.durum, gorev.tekrar_sayisi) == ("bekliyor", 1)
    assert "OSError" in gorev.hata_mesaji
    assert _belge_durumu(conn, sonuc["id"]) == "isleniyor"

    # Bekleme süresi dolmadan görev yeniden alınmaz
    assert gorevi_isle(conn, depolama) != gorev_id
    assert _gorev(conn, gorev_id).tekrar_sayisi == 1

    # Süre dolunca alınır ve bu kez başarılı olur
    _geri_al(conn, gorev_id, 61)
    assert gorevi_isle(conn, depolama) == gorev_id
    gorev = _gorev(conn, gorev_id)
    assert (gorev.durum, gorev.tekrar_sayisi) == ("tamam", 1)
    assert _belge_durumu(conn, sonuc["id"]) == "hazir"


def test_bekleme_suresi_her_denemede_iki_katina_cikar(conn, dava, tmp_path):
    depolama = AksayanDepolama(tmp_path, hata_sayisi=2)
    gorev_id = _yukle(conn, dava, depolama)["metin_cikarma_gorevi_id"]

    gorevi_isle(conn, depolama)          # 1. başarısız deneme
    _geri_al(conn, gorev_id, 61)
    gorevi_isle(conn, depolama)          # 2. başarısız deneme; bekleme artık 120 sn
    assert _gorev(conn, gorev_id).tekrar_sayisi == 2

    _geri_al(conn, gorev_id, 90)
    assert gorevi_isle(conn, depolama) != gorev_id
    _geri_al(conn, gorev_id, 121)
    assert gorevi_isle(conn, depolama) == gorev_id
    assert _gorev(conn, gorev_id).durum == "tamam"


def test_deneme_hakki_bitince_gorev_hataya_duser(conn, dava, tmp_path, monkeypatch):
    monkeypatch.setattr(ayarlar, "YENIDEN_DENEME_TABAN_SANIYE", 0)
    depolama = AksayanDepolama(tmp_path, hata_sayisi=10)
    sonuc = _yukle(conn, dava, depolama)
    gorev_id = sonuc["metin_cikarma_gorevi_id"]

    for _ in range(3):
        assert gorevi_isle(conn, depolama) == gorev_id
    gorev = _gorev(conn, gorev_id)
    assert (gorev.durum, gorev.tekrar_sayisi) == ("hata", 3)
    assert _belge_durumu(conn, sonuc["id"]) == "hata"
    # Hataya düşen görev bir daha alınmaz
    assert gorevi_isle(conn, depolama) != gorev_id


def test_kalici_hata_yeniden_denenmez(conn, dava, tmp_path, monkeypatch):
    monkeypatch.setattr(ayarlar, "YENIDEN_DENEME_TABAN_SANIYE", 0)
    depolama = YerelDepolama(tmp_path)
    sonuc = belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                        orijinal_ad="bozuk.pdf", veri=b"%PDF-1.4\nbozuk icerik")
    gorev_id = sonuc["metin_cikarma_gorevi_id"]

    assert gorevi_isle(conn, depolama) == gorev_id
    gorev = _gorev(conn, gorev_id)
    assert (gorev.durum, gorev.tekrar_sayisi) == ("hata", 1)
    assert "KaliciHata" in gorev.hata_mesaji
    assert gorevi_isle(conn, depolama) != gorev_id
