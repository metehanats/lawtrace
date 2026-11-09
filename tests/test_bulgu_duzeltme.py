"""Bulgu düzeltme: avukat yanlış okunan değeri kaynağı aynı kalarak düzeltir. Veriler sentetiktir."""

import pytest
from sqlalchemy import text

from app.analiz.hizmet import deger_ayristir
from app.belge.erisim import BelgeHatasi
from conftest import ekle
from test_celiski import _analiz, _celiskiler, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)


@pytest.mark.parametrize("tur, girilen, onceki, beklenen", [
    ("tarih", "17.03.2025", "2025-03-18", "2025-03-17"),
    ("tarih", "17 Mart 2025", "2025-03-18", "2025-03-17"),
    ("tutar", "386.420,50 TL", "368420.50 TRY", "386420.50 TRY"),
    ("tutar", "386.420,50", "368420.50 TRY", "386420.50 TRY"),      # birim yazılmazsa bulgununki
    ("tutar", "1.500", "1400.00 USD", "1500.00 USD"),
    ("kisi", "  Av. Ayşe   Yılmaz ", "Ayse Yilmaz", "Ayşe Yılmaz"),
])
def test_girilen_deger_saklama_bicimine_cevrilir(tur, girilen, onceki, beklenen):
    assert deger_ayristir(tur, girilen, onceki) == beklenen


@pytest.mark.parametrize("tur, girilen", [("tarih", "32.13.2025"), ("tarih", "geçen ay"), ("tutar", "çok"),
                                          ("kisi", " "), ("kisi", "A")])
def test_anlasilmayan_deger_reddedilir(tur, girilen):
    with pytest.raises(BelgeHatasi):
        deger_ayristir(tur, girilen, "368420.50 TRY")


def _bulgular(istemci, dava):
    return _istek(istemci, "GET", f"/davalar/{dava['dava']}/bulgular", dava["kullanici"]).json()["bulgular"]


def test_duzeltme_celiskiyi_kaldirir_kaynagi_korur_ve_yeniden_analizde_kalir(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dava dilekçesi.docx", "Dava değeri: 386.420,50 TL")
    _yukle(conn, acik, depolama, "Bilirkişi raporu.docx", "Hesaplanan dava değeri 368.420,50 TL olarak bulunmuştur.")
    _analiz(conn, istemci, acik, depolama)
    assert [c["tur"] for c in _celiskiler(istemci, acik)] == ["tutar"]
    yanlis = next(b for b in _bulgular(istemci, acik) if b["ozet"] == "368.420,50 TL")

    # Avukat kaynağa bakıp OCR/yazım hatası olduğuna karar verir; birim yazmadan düzeltir
    yanit = _istek(istemci, "POST", f"/bulgular/{yanlis['id']}/duzeltme", acik["kullanici"],
                   json={"deger": "386.420,50", "notu": "Raporun ekindeki tabloyla karşılaştırıldı"})
    assert yanit.status_code == 200 and yanit.json()["ozet"] == "386.420,50 TL"

    duzeltilen = next(b for b in _bulgular(istemci, acik) if b["id"] == yanlis["id"])
    assert (duzeltilen["ozet"], duzeltilen["dogrulama_durumu"], duzeltilen["son_karar"]) == (
        "386.420,50 TL", "onaylandi", "duzeltme")
    assert duzeltilen["duzeltme_onceki"] == "368.420,50 TL"
    assert duzeltilen["son_not"] == "Raporun ekindeki tabloyla karşılaştırıldı"
    # Kaynak değişmedi: aynı belge, sayfa ve alıntı
    assert (duzeltilen["belge_adi"], duzeltilen["alinti_metni"]) == (yanlis["belge_adi"], yanlis["alinti_metni"])
    # İki kaynak artık aynı değerde: tek grupta, çelişki kalktı
    assert len({b["grup_anahtari"] for b in _bulgular(istemci, acik) if b["tur"] == "tutar"}) == 1
    assert _celiskiler(istemci, acik) == []
    ayrinti = conn.execute(text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = 'guncelleme' AND hedef_id = :b"),
                           {"b": yanlis["id"]}).scalar_one()
    assert ayrinti == {"islem": "duzeltme", "onceki": "368.420,50 TL", "yeni": "386.420,50 TL"}

    # Yeniden analiz düzeltilmiş (onaylı) bulguyu ezmez
    _analiz(conn, istemci, acik, depolama)
    sonra = next(b for b in _bulgular(istemci, acik) if b["id"] == yanlis["id"])
    assert (sonra["ozet"], sonra["dogrulama_durumu"]) == ("386.420,50 TL", "onaylandi")
    assert _celiskiler(istemci, acik) == []


def test_ayni_deger_ve_gecersiz_deger_422_stajyer_duzeltemez(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dilekçe.docx", "Sözleşme tarihi 03.11.2024 olup teslim yapılmıştır.")
    _analiz(conn, istemci, acik, depolama)
    tarih = next(b for b in _bulgular(istemci, acik) if b["tur"] == "tarih")
    yol = f"/bulgular/{tarih['id']}/duzeltme"
    ayni = _istek(istemci, "POST", yol, acik["kullanici"], json={"deger": "3 Kasım 2024"})
    assert ayni.status_code == 422 and "onaylayın" in ayni.json()["detail"]
    assert _istek(istemci, "POST", yol, acik["kullanici"], json={"deger": "31.02.2024x"}).status_code == 422

    stajyer = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Stj', 'stj-duzeltme@ornek.test', 'stajyer')", b=acik["buro"])
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": acik["dava"], "k": stajyer})
    assert _istek(istemci, "POST", yol, stajyer, json={"deger": "04.11.2024"}).status_code == 403
    assert next(b for b in _bulgular(istemci, acik) if b["id"] == tarih["id"])["ozet"] == "03.11.2024"
