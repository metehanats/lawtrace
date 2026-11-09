"""OCR testleri. Taranmış sayfa, sentetik metinden üretilmiş bir görüntüdür.

Tesseract ve Türkçe dil dosyası kurulu değilse gerçek OCR testleri atlanır.
"""

import shutil
from pathlib import Path

import pytest
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import text

from app import ayarlar
from app.belge.depolama import YerelDepolama
from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle

TARANMIS_SATIRLAR = [
    "Davacı: Ayşe Yılmaz",
    "Ödeme tutarı: 12.500 TL",
    "Tarih: 14.03.2026",
]


def _tesseract_hazir() -> bool:
    yol = ayarlar.tesseract_yolu()
    var = Path(yol).exists() or shutil.which(yol)
    return bool(var) and (ayarlar.tessdata_dizini() / "tur.traineddata").exists()


ocr_gerekli = pytest.mark.skipif(not _tesseract_hazir(), reason="Tesseract veya Türkçe dil dosyası kurulu değil.")


def taranmis_sayfa(satirlar: list[str]) -> Image.Image:
    """A4 boyutunda (300 dpi), metni yalnızca görüntü olarak içeren bir sayfa."""
    goruntu = Image.new("L", (2480, 3508), color=255)
    cizim = ImageDraw.Draw(goruntu)
    font = ImageFont.truetype(r"C:\Windows\Fonts\arial.ttf", 64)
    for i, satir in enumerate(satirlar):
        cizim.text((200, 300 + i * 120), satir, fill=0, font=font)
    return goruntu


def pdf_uret(*sayfalar) -> bytes:
    """str argüman metinli sayfa, Image argüman taranmış sayfa olur."""
    pdf = FPDF()
    pdf.set_font("helvetica", size=12)
    for sayfa in sayfalar:
        pdf.add_page()
        if isinstance(sayfa, Image.Image):
            pdf.image(sayfa, x=0, y=0, w=210)
        else:
            pdf.multi_cell(0, 10, sayfa)
    return bytes(pdf.output())


@pytest.fixture
def depolama(tmp_path):
    return YerelDepolama(tmp_path)


def _yukle(conn, dava, depolama, veri):
    return belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                       orijinal_ad="taranmis.pdf", veri=veri)


def _sayfalar(conn, belge_id):
    return conn.execute(
        text(
            "SELECT sayfa_no, metin, metin_kaynagi, ocr_guven_skoru FROM belge_sayfa "
            "WHERE belge_id = :b ORDER BY sayfa_no"
        ),
        {"b": belge_id},
    ).all()


def _ocr_gorevi(conn, belge_id):
    return conn.execute(
        text("SELECT id, durum, tekrar_sayisi, hata_mesaji FROM isleme_gorevi WHERE belge_id = :b AND adim = 'ocr'"),
        {"b": belge_id},
    ).one()


@ocr_gerekli
def test_taranmis_sayfa_ocr_ile_okunur(conn, dava, depolama):
    sonuc = _yukle(conn, dava, depolama, pdf_uret("Dijital sayfa", taranmis_sayfa(TARANMIS_SATIRLAR)))
    gorevi_isle(conn, depolama)  # metin çıkarma: 2. sayfa boş çıkar, OCR görevi açılır
    ocr_gorevi = _ocr_gorevi(conn, sonuc["id"])
    assert gorevi_isle(conn, depolama) == ocr_gorevi.id

    dijital, taranmis = _sayfalar(conn, sonuc["id"])
    # Metinli sayfaya dokunulmaz
    assert (dijital.metin_kaynagi, dijital.ocr_guven_skoru) == ("dogrudan", None)
    assert "Dijital" in dijital.metin

    assert taranmis.metin_kaynagi == "ocr"
    for beklenen in ["Ayşe Yılmaz", "Ödeme", "12.500 TL", "14.03.2026"]:
        assert beklenen in taranmis.metin, (beklenen, taranmis.metin)
    assert 0.8 <= taranmis.ocr_guven_skoru <= 1

    assert _ocr_gorevi(conn, sonuc["id"]).durum == "tamam"
    durum = conn.execute(text("SELECT durum FROM belge WHERE id = :b"), {"b": sonuc["id"]}).scalar_one()
    assert durum == "hazir"


@ocr_gerekli
def test_bos_taranmis_sayfa_skorsuz_kalir(conn, dava, depolama):
    sonuc = _yukle(conn, dava, depolama, pdf_uret(taranmis_sayfa([])))
    gorevi_isle(conn, depolama)
    gorevi_isle(conn, depolama)
    (sayfa,) = _sayfalar(conn, sonuc["id"])
    assert (sayfa.metin, sayfa.metin_kaynagi, sayfa.ocr_guven_skoru) == ("", "ocr", None)


def test_tesseract_bulunamazsa_gecici_hata_sayilir(conn, dava, depolama, monkeypatch):
    monkeypatch.setenv("TESSERACT_YOLU", r"C:\yok\tesseract.exe")
    sonuc = _yukle(conn, dava, depolama, pdf_uret(taranmis_sayfa(["Sentetik"])))
    gorevi_isle(conn, depolama)
    gorevi_isle(conn, depolama)
    gorev = _ocr_gorevi(conn, sonuc["id"])
    assert (gorev.durum, gorev.tekrar_sayisi) == ("bekliyor", 1)
    assert "FileNotFoundError" in gorev.hata_mesaji
    # Yarım OCR kaydedilmez; sayfa hâlâ OCR bekler
    (sayfa,) = _sayfalar(conn, sonuc["id"])
    assert (sayfa.metin, sayfa.metin_kaynagi) == ("", "dogrudan")
