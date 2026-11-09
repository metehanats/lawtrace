"""Belge yükleme ve metin çıkarma testleri. Tüm belgeler sentetiktir."""

import hashlib
import io

import docx
import pytest
from fpdf import FPDF
from sqlalchemy import text

from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import DOCX, PDF, belge_yukle, tur_belirle
from conftest import ekle


def pdf_uret(*sayfalar: str) -> bytes:
    """Her argüman bir sayfa olur; boş metin, metinsiz (taranmış gibi) sayfa üretir."""
    pdf = FPDF()
    pdf.set_font("helvetica", size=12)
    for metin in sayfalar:
        pdf.add_page()
        if metin:
            pdf.multi_cell(0, 10, metin)
    return bytes(pdf.output())


def docx_uret(*sayfalar: str) -> bytes:
    belge = docx.Document()
    for i, metin in enumerate(sayfalar):
        if i:
            belge.add_page_break()
        belge.add_paragraph(metin)
    tampon = io.BytesIO()
    belge.save(tampon)
    return tampon.getvalue()


def _yukle(istemci, dava, veri, ad="dilekce.pdf", kullanici=None):
    return istemci.post(
        f"/davalar/{dava['dava']}/belgeler",
        files={"dosya": (ad, veri, "application/octet-stream")},
        headers={"X-Kullanici-Id": str(kullanici or dava["kullanici"])},
    )


# --- Tür belirleme ---------------------------------------

def test_tur_icerige_gore_belirlenir():
    assert tur_belirle(pdf_uret("x")) == PDF
    assert tur_belirle(docx_uret("x")) == DOCX
    assert tur_belirle(b"\x89PNG\r\n\x1a\n") is None
    # Word olmayan bir zip dosyası kabul edilmez
    tampon = io.BytesIO()
    import zipfile
    with zipfile.ZipFile(tampon, "w") as z:
        z.writestr("baska.txt", "x")
    assert tur_belirle(tampon.getvalue()) is None


# --- Yükleme ---------------------------------------------

def test_pdf_yuklenir_gorev_ve_denetim_kaydi_olusur(conn, dava, istemci, depolama):
    veri = pdf_uret("Sentetik dilekce metni")
    yanit = _yukle(istemci, dava, veri)
    assert yanit.status_code == 201, yanit.text
    govde = yanit.json()
    assert govde["mime_tur"] == PDF
    assert govde["sha256_ozet"] == hashlib.sha256(veri).hexdigest()

    belge = conn.execute(
        text("SELECT orijinal_ad, durum, depolama_anahtari FROM belge WHERE id = :i"),
        {"i": govde["id"]},
    ).one()
    assert belge.orijinal_ad == "dilekce.pdf"
    assert belge.durum == "yuklendi"
    assert "dilekce" not in belge.depolama_anahtari
    assert depolama.oku(belge.depolama_anahtari) == veri

    gorev = conn.execute(
        text("SELECT adim, durum FROM isleme_gorevi WHERE id = :i"),
        {"i": govde["metin_cikarma_gorevi_id"]},
    ).one()
    assert (gorev.adim, gorev.durum) == ("metin_cikarma", "bekliyor")

    denetim = conn.execute(
        text("SELECT count(*) FROM denetim_kaydi WHERE eylem = 'yukleme' AND hedef_id = :i"),
        {"i": govde["id"]},
    ).scalar_one()
    assert denetim == 1


def test_ayni_belge_ikinci_kez_reddedilir(dava, istemci):
    veri = pdf_uret("Ayni belge")
    assert _yukle(istemci, dava, veri).status_code == 201
    assert _yukle(istemci, dava, veri, ad="kopya.pdf").status_code == 409


def test_desteklenmeyen_tur_reddedilir(dava, istemci):
    # Uzantı .pdf olsa da içerik PDF değil
    assert _yukle(istemci, dava, b"\x89PNG\r\n\x1a\nveri", ad="sahte.pdf").status_code == 415


def test_bos_dosya_reddedilir(dava, istemci):
    assert _yukle(istemci, dava, b"").status_code == 400


def test_boyut_siniri(conn, dava, depolama, monkeypatch):
    from app import ayarlar
    from app.belge.yukleme import YuklemeHatasi

    monkeypatch.setattr(ayarlar, "MAKS_BELGE_BOYUTU", 10)
    with pytest.raises(YuklemeHatasi) as hata:
        belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                    orijinal_ad="buyuk.pdf", veri=pdf_uret("x"))
    assert hata.value.kod == 413


def test_dosya_erisimi_olmayan_avukat_yukleyemez(conn, dava, istemci):
    yetkisiz = ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yetkisiz', 'yetkisiz@ornek.test', 'avukat')",
        b=dava["buro"],
    )
    assert _yukle(istemci, dava, pdf_uret("x"), kullanici=yetkisiz).status_code == 403


def test_buro_yoneticisi_erisim_kaydi_olmadan_yukleyebilir(conn, dava, istemci):
    yonetici = ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Yönetici', 'yonetici@ornek.test', 'yonetici')",
        b=dava["buro"],
    )
    assert _yukle(istemci, dava, pdf_uret("x"), kullanici=yonetici).status_code == 201


def test_baska_buronun_dosyasi_gorunmez(conn, dava, istemci):
    diger_buro = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yabancı', 'yabanci@ornek.test', 'yonetici')",
        b=diger_buro,
    )
    assert _yukle(istemci, dava, pdf_uret("x"), kullanici=yabanci).status_code == 404


# --- Metin çıkarma ---------------------------------------

def _yukle_ve_isle(conn, dava, depolama, veri):
    sonuc = belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                        orijinal_ad="belge", veri=veri)
    assert gorevi_isle(conn, depolama) == sonuc["metin_cikarma_gorevi_id"]
    return sonuc["id"]


def _sayfalar(conn, belge_id):
    return conn.execute(
        text("SELECT sayfa_no, metin, metin_kaynagi FROM belge_sayfa WHERE belge_id = :b ORDER BY sayfa_no"),
        {"b": belge_id},
    ).all()


def _belge(conn, belge_id):
    return conn.execute(
        text("SELECT durum, sayfa_sayisi FROM belge WHERE id = :b"), {"b": belge_id}
    ).one()


def test_pdf_sayfa_sayfa_cikarilir(conn, dava, depolama):
    belge_id = _yukle_ve_isle(conn, dava, depolama, pdf_uret("Birinci sayfa", "Ikinci sayfa"))
    sayfalar = _sayfalar(conn, belge_id)
    assert [s.sayfa_no for s in sayfalar] == [1, 2]
    assert "Birinci" in sayfalar[0].metin and "Ikinci" in sayfalar[1].metin
    assert all(s.metin_kaynagi == "dogrudan" for s in sayfalar)
    assert tuple(_belge(conn, belge_id)) == ("hazir", 2)


def test_docx_sayfa_sonlarina_gore_bolunur_turkce_korunur(conn, dava, depolama):
    belge_id = _yukle_ve_isle(conn, dava, depolama,
                              docx_uret("Davacı: Ayşe Yılmaz", "Ödeme: 12.500 TL, ığüşöç"))
    sayfalar = _sayfalar(conn, belge_id)
    assert [s.metin for s in sayfalar] == ["Davacı: Ayşe Yılmaz", "Ödeme: 12.500 TL, ığüşöç"]
    assert tuple(_belge(conn, belge_id)) == ("hazir", 2)


def test_metinsiz_pdf_sayfasi_icin_ocr_gorevi_acilir(conn, dava, depolama):
    belge_id = _yukle_ve_isle(conn, dava, depolama, pdf_uret("Metinli sayfa", ""))
    ocr = conn.execute(
        text("SELECT durum FROM isleme_gorevi WHERE belge_id = :b AND adim = 'ocr'"), {"b": belge_id}
    ).scalar_one()
    assert ocr == "bekliyor"
    # OCR bitmeden belge hazır sayılmaz
    assert _belge(conn, belge_id).durum == "isleniyor"


def test_bozuk_pdf_gorevi_hataya_dusurur(conn, dava, depolama):
    sonuc = belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                        orijinal_ad="bozuk.pdf", veri=b"%PDF-1.4\nbozuk icerik")
    gorevi_isle(conn, depolama)
    gorev = conn.execute(
        text("SELECT durum, hata_mesaji, tekrar_sayisi FROM isleme_gorevi WHERE id = :g"),
        {"g": sonuc["metin_cikarma_gorevi_id"]},
    ).one()
    assert gorev.durum == "hata" and gorev.hata_mesaji and gorev.tekrar_sayisi == 1
    assert _belge(conn, sonuc["id"]).durum == "hata"
    assert _sayfalar(conn, sonuc["id"]) == []


def test_bekleyen_gorev_yoksa_none(conn, depolama):
    # Bu test işlemi içinde başka bekleyen görev yoksa
    if conn.execute(text(
        "SELECT count(*) FROM isleme_gorevi WHERE adim IN ('metin_cikarma', 'ocr') AND durum = 'bekliyor'"
    )).scalar_one() == 0:
        assert gorevi_isle(conn, depolama) is None
