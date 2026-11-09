"""Çelişki tespiti testleri: etiket okuma, kurallar ve uygulama akışı. Tüm veriler sentetiktir."""

import itertools

import pytest
from sqlalchemy import text

import app.analiz.gorev as gorev_mod
from app.analiz.celiski import CeliskiBulgusu, celiskileri_bul, etiket_bul
from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle
from test_belge import docx_uret

_sayac = itertools.count()


def _konum(metin: str, deger_metni: str) -> tuple[int, int]:
    i = metin.index(deger_metni)
    return i, i + len(deger_metni)


@pytest.mark.parametrize("metin, deger, tur, beklenen", [
    ("Dava Değeri: 1.248.750,00 TL", "1.248.750,00 TL", "tutar", "dava değeri"),
    ("KONU: 386.420,50 TL asıl alacağın tahsili", "386.420,50 TL", "tutar", "asıl alacak"),
    ("Son aylık net ücreti 38.750,00.-TL olup", "38.750,00.-TL", "tutar", "son ücret"),
    ("Sözleşme tarihi 03.11.2024 olup ihtarname 17.02.2025 tarihinde tebliğ", "03.11.2024", "tarih",
     "sözleşme tarihi"),
    # İhtarname ile tebliğ aynı cümlede: tarih tebliğ tarihidir (gönderme tarihiyle çelişki sayılmasın)
    ("Sözleşme tarihi 03.11.2024 olup ihtarname 17.02.2025 tarihinde tebliğ", "17.02.2025", "tarih",
     "tebliğ tarihi"),
    ("Davalıya 17.02.2025 tarihinde ihtarname gönderilmiştir.", "17.02.2025", "tarih", "ihtarname tarihi"),
    # İki parçalı: değer araya girer
    ("Sözleşme 03.11.2024 tarihinde imzalanmıştır.", "03.11.2024", "tarih", "sözleşme tarihi"),
    # Cümle sınırı aşılmaz
    ("Fatura 05.12.2024 tarihlidir. Dava değeri 10.000 TL'dir.", "05.12.2024", "tarih", None),
    ("28 Şubat 2025'de iş akdi feshedilmiştir", "28 Şubat 2025", "tarih", "fesih tarihi"),
    # Ek ve çatı değişimleri (demo belgelerinde kaçırılmıştı)
    ("davalı şirketle 03.11.2024 tarihinde mal satış sözleşmesi imzalamış", "03.11.2024", "tarih",
     "sözleşme tarihi"),
    ("Sözleşme 03.11.2024 tarihinde imzalanmıştır; sözleşme imzalandı", "03.11.2024", "tarih", "sözleşme tarihi"),
    ("İncelenen faturaların toplam tutarı 386.420,50 TL olup", "386.420,50 TL", "tutar", "talep edilen toplam"),
    ("Davacının talep edebileceği alacak tutarı 386.420,50 TL'dir.", "386.420,50 TL", "tutar",
     "talep edilen toplam"),
    # Birden çok değeri olabilen etiketler: etiket yok sayılır
    ("- 03.11.2024 tarihli fatura: 120.000,00 TL", "120.000,00 TL", "tutar", None),
    ("- 03.11.2024 tarihli fatura: 120.000,00 TL", "03.11.2024", "tarih", None),
    # Etiket başka satırda ise sayılmaz
    ("Dava değeri aşağıdadır.\n120.000 TL ödendi", "120.000 TL", "tutar", None),
])
def test_etiket_bul(metin, deger, tur, beklenen):
    assert etiket_bul(metin, *_konum(metin, deger), tur) == beklenen


def _b(tur, deger, belge="Dilekçe", etiket=None, durum="otomatik", ocr=False, ozet=None):
    return CeliskiBulgusu(next(_sayac), tur, deger, ozet or deger, etiket, belge, belge, 1, durum, ocr)


def test_ayni_etiket_farkli_tutar_celiskidir():
    (c,) = celiskileri_bul([_b("tutar", "386420.50 TRY", "Dilekçe", "dava değeri"),
                            _b("tutar", "368420.50 TRY", "Cevap", "dava değeri")])
    assert (c.tur, c.ciddiyet) == ("tutar", "yuksek") and "dava değeri" in c.aciklama


def test_ayni_deger_ya_da_etiketsiz_ya_da_cok_degerli_etiket_celiski_degildir():
    assert celiskileri_bul([_b("tutar", "386420.50 TRY", "Dilekçe", "dava değeri"),
                            _b("tutar", "386420.50 TRY", "Rapor", "dava değeri")]) == []
    assert celiskileri_bul([_b("tutar", "1.00 TRY"), _b("tutar", "2.00 TRY")]) == []


def test_reddedilen_bulgu_celiski_yaratmaz():
    assert celiskileri_bul([_b("tarih", "2024-11-03", etiket="sözleşme tarihi"),
                            _b("tarih", "2024-11-04", "Cevap", "sözleşme tarihi", durum="reddedildi")]) == []


def test_tarih_celiskisi_orta_onemli():
    (c,) = celiskileri_bul([_b("tarih", "2024-11-03", etiket="sözleşme tarihi"),
                            _b("tarih", "2024-11-04", "Cevap", "sözleşme tarihi")])
    assert (c.tur, c.ciddiyet) == ("tarih", "orta")


@pytest.mark.parametrize("a, b, celiski_mi", [
    ("İsmail Güneş", "İsmail Gunes", True),          # harf farkı: yazım hatası olabilir
    ("Ayşe Yılmaz", "Ayse Yilmaz", True),
    ("Mehmet Öztürk", "Mehmet. Öztürk", False),       # yalnızca noktalama (OCR)
    ("Ali Kaya", "Veli Kaya", False),                 # farklı kişiler
    ("Ayşe Yılmaz", "AYŞE YILMAZ", False),            # yalnızca büyük/küçük harf
])
def test_ad_yazim_farki(a, b, celiski_mi):
    sonuc = celiskileri_bul([_b("kisi", a), _b("kisi", b, "Cevap")])
    assert bool(sonuc) is celiski_mi
    if sonuc:
        assert (sonuc[0].tur, sonuc[0].ciddiyet) == ("kisi_kurum", "dusuk")


def test_supheli_ocr_sayfasindaki_yazim_farki_sayilmaz():
    assert celiskileri_bul([_b("kisi", "İsmail Güneş"), _b("kisi", "İsmail Gunes", "Faks", ocr=True)]) == []


# --- Uygulama akışı (sahte model, gerçek veritabanı/işçi/API) ----------------

class SahteModel:
    saglayici, model = "ollama", "sahte"

    def json_tamamla(self, sistem, kullanici, sema):
        return {"bulgular": []}


@pytest.fixture
def acik(conn, dava, monkeypatch):
    monkeypatch.setattr(gorev_mod, "model_olustur", lambda tanim: SahteModel())
    conn.execute(text("UPDATE buro SET analiz_modeli = 'ollama:sahte' WHERE id = :b"), {"b": dava["buro"]})
    return dava


def _istek(istemci, yontem, yol, kullanici, **kw):
    return istemci.request(yontem, yol, headers={"X-Kullanici-Id": str(kullanici)}, **kw)


def _yukle(conn, dava, depolama, ad, *sayfalar):
    belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"], orijinal_ad=ad,
                veri=docx_uret(*sayfalar))
    gorevi_isle(conn, depolama, ("metin_cikarma",))


def _analiz(conn, istemci, dava, depolama):
    _istek(istemci, "POST", f"/davalar/{dava['dava']}/analiz", dava["kullanici"], json={})
    while gorevi_isle(conn, depolama, ("analiz",)):
        pass


def _celiskiler(istemci, dava):
    return _istek(istemci, "GET", f"/davalar/{dava['dava']}/celiskiler", dava["kullanici"]).json()["celiskiler"]


def test_belgeler_arasi_celiski_bulunur_red_ile_kalkar_inceleme_korunur(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dava dilekçesi.docx",
           "Dava değeri: 386.420,50 TL\nSözleşme tarihi 03.11.2024 olup teslim yapılmıştır.")
    _yukle(conn, acik, depolama, "Cevap dilekçesi.docx",
           "Davacının iddia ettiği dava değeri 368.420,50 TL yanlıştır.\n"
           "Sözleşme tarihi 04.11.2024'tür.\n"
           "- 05.12.2024 tarihli fatura: 10.000 TL\n- 06.12.2024 tarihli fatura: 12.000 TL")
    _analiz(conn, istemci, acik, depolama)

    celiskiler = _celiskiler(istemci, acik)
    assert sorted((c["tur"], c["ciddiyet"]) for c in celiskiler) == [("tarih", "orta"), ("tutar", "yuksek")]
    tutar = next(c for c in celiskiler if c["tur"] == "tutar")
    assert {tutar["bulgu_1"]["ozet"], tutar["bulgu_2"]["ozet"]} == {"386.420,50 TL", "368.420,50 TL"}
    assert {tutar["bulgu_1"]["belge_adi"], tutar["bulgu_2"]["belge_adi"]} == {"Dava dilekçesi.docx",
                                                                              "Cevap dilekçesi.docx"}
    # Faturaların farklı tarih ve tutarları çelişki sayılmadı

    # Avukat sözleşme tarihi çelişkisini "incelendi" yapar; yeniden analizde korunur
    tarih = next(c for c in celiskiler if c["tur"] == "tarih")
    assert _istek(istemci, "PUT", f"/celiskiler/{tarih['id']}", acik["kullanici"],
                  json={"durum": "incelendi"}).status_code == 204

    # Avukat hatalı tutar bulgusunu reddeder: tutar çelişkisi kalkar
    yanlis = tutar["bulgu_1"] if tutar["bulgu_1"]["ozet"] == "368.420,50 TL" else tutar["bulgu_2"]
    _istek(istemci, "POST", f"/bulgular/{yanlis['id']}/inceleme", acik["kullanici"], json={"karar": "red"})
    sonra = _celiskiler(istemci, acik)
    assert [(c["tur"], c["durum"]) for c in sonra] == [("tarih", "incelendi")]

    # Bulgu listesi grup anahtarı ve etiket taşır
    bulgular = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"]
    dava_degeri = [b for b in bulgular if b["etiket"] == "dava değeri"]
    assert {b["grup_anahtari"] for b in dava_degeri} == {"tutar:386420.50 TRY", "tutar:368420.50 TRY"}


def test_stajyer_celiski_durumunu_degistiremez(conn, acik, depolama, istemci):
    from conftest import ekle
    _yukle(conn, acik, depolama, "A.docx", "Dava değeri: 1.000 TL")
    _yukle(conn, acik, depolama, "B.docx", "Dava değeri: 2.000 TL")
    _analiz(conn, istemci, acik, depolama)
    (c,) = _celiskiler(istemci, acik)
    stajyer = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Stj', 'stj-celiski@ornek.test', 'stajyer')", b=acik["buro"])
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": acik["dava"], "k": stajyer})
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}/celiskiler", stajyer).status_code == 200
    assert _istek(istemci, "PUT", f"/celiskiler/{c['id']}", stajyer, json={"durum": "cozuldu"}).status_code == 403
