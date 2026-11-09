"""Analizin uygulamaya bağlanması: başlatma, işçi, bulgu kaydı, özel nitelik kapısı, avukat incelemesi.

Gerçek dil modeli kullanılmaz; sahte model önceden belirlenmiş kişi/kurum yanıtı verir.
Veritabanı, işçi ve API gerçektir. Tüm belgeler sentetiktir.
"""

import uuid

import pytest
from sqlalchemy import text

import app.analiz.gorev as gorev_mod
from app.analiz.gorev import bulgu_ozeti
from app.analiz.modeller import ModelHatasi
from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle
from conftest import ekle
from test_belge import pdf_uret

METIN = "Davaci Ayse Yilmaz 03.11.2024 tarihinde 386.420,50 TL odeme yapmadigini bildirdi."


class SahteModel:
    saglayici, model = "ollama", "sahte"
    yanit = {"bulgular": [{"tur": "kisi", "deger": "Ayse Yilmaz", "alinti": "Davaci Ayse Yilmaz", "sayfa": 1}]}

    def json_tamamla(self, sistem, kullanici, sema):
        return self.yanit


@pytest.fixture(autouse=True)
def sahte_model(monkeypatch):
    monkeypatch.setattr(gorev_mod, "model_olustur", lambda tanim: SahteModel())


@pytest.fixture
def acik(conn, dava):
    conn.execute(text("UPDATE buro SET analiz_modeli = 'ollama:sahte' WHERE id = :b"), {"b": dava["buro"]})
    return dava


def _istek(istemci, yontem, yol, kullanici, **kw):
    return istemci.request(yontem, yol, headers={"X-Kullanici-Id": str(kullanici)}, **kw)


def _hazir_belge(conn, dava, depolama, metin=METIN, ad="dilekce.pdf"):
    belge_id = belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                           orijinal_ad=ad, veri=pdf_uret(metin))["id"]
    gorevi_isle(conn, depolama, ("metin_cikarma",))
    return belge_id


def _isle(conn, depolama):
    return gorevi_isle(conn, depolama, ("analiz",))


def _stajyer(conn, dava):
    return ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) VALUES (:b, 'Stj', :e, 'stajyer')",
                b=dava["buro"], e=f"{uuid.uuid4().hex[:6]}@ornek.test")


def _denetim(conn, eylem, hedef_id):
    return conn.execute(text("SELECT count(*) FROM denetim_kaydi WHERE eylem = :e AND hedef_id = :h"),
                        {"e": eylem, "h": hedef_id}).scalar_one()


@pytest.mark.parametrize("tur, deger, ozet", [
    ("tutar", "386420.50 TRY", "386.420,50 TL"), ("tutar", "2000.00 USD", "2.000,00 USD"),
    ("tarih", "2024-11-03", "03.11.2024"), ("tarih", "2020-03", "Mart 2020"), ("tarih", "2021", "2021"),
    ("kisi", "Ayşe Yılmaz", "Ayşe Yılmaz"),
])
def test_bulgu_ozeti(tur, deger, ozet):
    assert bulgu_ozeti(tur, deger) == ozet


def test_buro_icin_kapaliysa_baslatilamaz(conn, dava, depolama, istemci):
    _hazir_belge(conn, dava, depolama)
    yanit = _istek(istemci, "POST", f"/davalar/{dava['dava']}/analiz", dava["kullanici"], json={})
    assert yanit.status_code == 409 and "kapalı" in yanit.json()["detail"]


def test_analiz_bulgulari_kaynaklariyla_kaydeder(conn, acik, depolama, istemci):
    belge_id = _hazir_belge(conn, acik, depolama)
    yanit = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    assert yanit.status_code == 202, yanit.text
    assert [b["belge_id"] for b in yanit.json()["baslatilan"]] == [str(belge_id)]
    assert _denetim(conn, "analiz", acik["dava"]) == 1

    assert _isle(conn, depolama) is not None
    durum = _istek(istemci, "GET", f"/davalar/{acik['dava']}/analiz", acik["kullanici"]).json()
    (b,) = durum["belgeler"]
    assert (b["analiz_durumu"], b["bulgu_sayisi"], durum["analiz_acik"]) == ("tamam", 3, True)

    bulgular = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"]
    ozet = {(x["tur"], x["ozet"], x["yontem"], x["guven_seviyesi"], x["dogrulama_durumu"]) for x in bulgular}
    assert ozet == {
        ("tarih", "03.11.2024", "kural", "yuksek", "otomatik"),
        ("tutar", "386.420,50 TL", "kural", "yuksek", "otomatik"),
        ("kisi", "Ayse Yilmaz", "model", "orta", "otomatik"),
    }
    # Her bulgunun alıntısı, kayıtlı sayfa metninde belirtilen konumda birebir durur
    for x in bulgular:
        sayfa = _istek(istemci, "GET", f"/belgeler/{x['belge_id']}/sayfalar/{x['sayfa_no']}", acik["kullanici"])
        assert sayfa.json()["metin"][x["karakter_baslangic"]:x["karakter_bitis"]] == x["alinti_metni"]


def test_metni_hazir_olmayan_ve_zaten_sirada_olan_atlanir(conn, acik, depolama, istemci):
    _hazir_belge(conn, acik, depolama)
    belge_yukle(conn, depolama, dava_id=acik["dava"], kullanici_id=acik["kullanici"], orijinal_ad="yeni.pdf",
                veri=pdf_uret("Henuz islenmedi"))
    ilk = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}).json()
    assert len(ilk["baslatilan"]) == 1 and ilk["atlanan"][0]["neden"] == "metni henüz hazır değil"
    ikinci = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}).json()
    assert ikinci["baslatilan"] == [] and {a["neden"] for a in ikinci["atlanan"]} == {
        "metni henüz hazır değil", "zaten analiz sırasında"}


def test_stajyer_baslatamaz_ve_karar_veremez_ama_gorur(conn, acik, depolama, istemci):
    stajyer = _stajyer(conn, acik)
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": acik["dava"], "k": stajyer})
    _hazir_belge(conn, acik, depolama)
    assert _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", stajyer, json={}).status_code == 403
    _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    _isle(conn, depolama)
    bulgular = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", stajyer).json()["bulgular"]
    assert len(bulgular) == 3
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}/analiz", stajyer).json()["karar_verebilir"] is False
    yanit = _istek(istemci, "POST", f"/bulgular/{bulgular[0]['id']}/inceleme", stajyer, json={"karar": "onay"})
    assert yanit.status_code == 403


def test_baska_buro_bulgulari_goremez(conn, acik, depolama, istemci):
    _hazir_belge(conn, acik, depolama)
    _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    _isle(conn, depolama)
    bulgu_id = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"][0]["id"]
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka')")
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Y', 'y@ornek.test', 'yonetici')", b=diger)
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", yabanci).status_code == 404
    assert _istek(istemci, "POST", f"/bulgular/{bulgu_id}/inceleme", yabanci, json={"karar": "onay"}).status_code == 404


# --- Özel nitelikli veri kapısı ---------------------------------------------

def test_ozel_nitelikli_belge_onaysiz_analiz_edilmez(conn, acik, depolama, istemci):
    belge_id = _hazir_belge(conn, acik, depolama, metin="Epikriz: hasta 03.11.2024 tarihinde hastaneye yatirildi.",
                            ad="saglik.pdf")
    durum = _istek(istemci, "GET", f"/davalar/{acik['dava']}/analiz", acik["kullanici"]).json()["belgeler"][0]
    assert durum["ozel_nitelikli"] is True and "epikriz" in durum["ozel_nitelik_nedeni"]

    yanit = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}).json()
    assert yanit["baslatilan"] == [] and yanit["onay_bekleyen"][0]["belge_id"] == str(belge_id)

    assert _istek(istemci, "POST", f"/belgeler/{belge_id}/ozel-nitelik-onayi", acik["kullanici"]).status_code == 204
    assert _denetim(conn, "onay", belge_id) == 1
    yanit = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}).json()
    assert len(yanit["baslatilan"]) == 1
    _isle(conn, depolama)
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}/analiz",
                  acik["kullanici"]).json()["belgeler"][0]["analiz_durumu"] == "tamam"


def test_isci_onaysiz_ozel_nitelikli_belgeyi_ikinci_kez_denetler(conn, acik, depolama):
    """API'yi atlayan bir analiz görevi bile onaysız özel nitelikli belgede çalışmaz; belge durumu bozulmaz."""
    belge_id = _hazir_belge(conn, acik, depolama, metin="Adli sicil kaydi bulunmaktadir.", ad="sicil.pdf")
    analiz_id = ekle(conn, "INSERT INTO analiz_calistirmasi (buro_id, dava_dosyasi_id, kapsam, belge_id, "
                           "model_saglayici, model_adi, prompt_surumu, calistiran_kullanici_id) "
                           "VALUES (:b, :d, 'tek_belge', :be, 'ollama', 'sahte', 'x', :k)",
                     b=acik["buro"], d=acik["dava"], be=belge_id, k=acik["kullanici"])
    conn.execute(text("INSERT INTO isleme_gorevi (belge_id, adim, analiz_calistirmasi_id) VALUES (:b, 'analiz', :a)"),
                 {"b": belge_id, "a": analiz_id})
    _isle(conn, depolama)
    gorev = conn.execute(text("SELECT durum, hata_mesaji FROM isleme_gorevi WHERE analiz_calistirmasi_id = :a"),
                         {"a": analiz_id}).one()
    assert gorev.durum == "hata" and "onayı yok" in gorev.hata_mesaji
    assert conn.execute(text("SELECT durum FROM analiz_calistirmasi WHERE id = :a"), {"a": analiz_id}).scalar_one() == "hata"
    assert conn.execute(text("SELECT durum FROM belge WHERE id = :b"), {"b": belge_id}).scalar_one() == "hazir"
    assert conn.execute(text("SELECT count(*) FROM bulgu WHERE analiz_calistirmasi_id = :a"),
                        {"a": analiz_id}).scalar_one() == 0


def test_elle_isaretleme_ve_isaret_kaldirinca_onay_duser(conn, acik, depolama, istemci):
    belge_id = _hazir_belge(conn, acik, depolama)
    yol = f"/belgeler/{belge_id}/ozel-nitelik"
    assert _istek(istemci, "PUT", yol, acik["kullanici"], json={"ozel_nitelikli": True, "neden": "Ekte rapor var"}
                  ).status_code == 204
    yanit = _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}).json()
    assert len(yanit["onay_bekleyen"]) == 1
    _istek(istemci, "POST", f"/belgeler/{belge_id}/ozel-nitelik-onayi", acik["kullanici"])
    _istek(istemci, "PUT", yol, acik["kullanici"], json={"ozel_nitelikli": False})
    b = conn.execute(text("SELECT ozel_nitelikli, ozel_nitelik_onay_zamani FROM belge WHERE id = :b"),
                     {"b": belge_id}).one()
    assert (b.ozel_nitelikli, b.ozel_nitelik_onay_zamani) == (False, None)
    assert _denetim(conn, "guncelleme", belge_id) == 2


# --- Avukat incelemesi ve yeniden analiz -----------------------------------

def test_inceleme_ve_yeniden_analizde_incelenenler_korunur(conn, acik, depolama, istemci):
    _hazir_belge(conn, acik, depolama)
    _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    _isle(conn, depolama)
    bulgular = {x["tur"]: x for x in
                _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"]}

    onay = _istek(istemci, "POST", f"/bulgular/{bulgular['tutar']['id']}/inceleme", acik["kullanici"],
                  json={"karar": "onay", "notu": "Fatura toplamıyla uyumlu"})
    assert onay.json()["dogrulama_durumu"] == "onaylandi"
    _istek(istemci, "POST", f"/bulgular/{bulgular['kisi']['id']}/inceleme", acik["kullanici"], json={"karar": "red"})
    assert _denetim(conn, "onay", bulgular["tutar"]["id"]) == 1
    assert _denetim(conn, "reddetme", bulgular["kisi"]["id"]) == 1

    # Yeniden analiz: incelenmemiş tarih yenilenir, onaylı tutar ve reddedilen kişi korunur, kopya oluşmaz
    _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    _isle(conn, depolama)
    yeni = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"]
    assert sorted((x["tur"], x["dogrulama_durumu"]) for x in yeni) == [
        ("kisi", "reddedildi"), ("tarih", "otomatik"), ("tutar", "onaylandi")]
    tutar = next(x for x in yeni if x["tur"] == "tutar")
    assert (tutar["son_karar"], tutar["son_not"]) == ("onay", "Fatura toplamıyla uyumlu")
    assert next(x for x in yeni if x["tur"] == "tarih")["id"] != bulgular["tarih"]["id"]


def test_model_hatasi_gecici_sayilir_belge_durumu_bozulmaz(conn, acik, depolama, istemci, monkeypatch):
    belge_id = _hazir_belge(conn, acik, depolama)

    class Bozuk:
        saglayici, model = "ollama", "bozuk"

        def json_tamamla(self, *a):
            raise ModelHatasi("Ollama'ya ulaşılamadı")

    monkeypatch.setattr(gorev_mod, "model_olustur", lambda tanim: Bozuk())
    _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={})
    _isle(conn, depolama)
    gorev = conn.execute(text("SELECT durum, tekrar_sayisi FROM isleme_gorevi WHERE belge_id = :b AND adim = 'analiz'"),
                         {"b": belge_id}).one()
    assert tuple(gorev) == ("bekliyor", 1)
    assert conn.execute(text("SELECT durum FROM belge WHERE id = :b"), {"b": belge_id}).scalar_one() == "hazir"
    # Yalnızca bu testin belgesi sayılır (veritabanında demo bulguları da olabilir)
    assert conn.execute(text("SELECT count(*) FROM kaynak_alinti WHERE belge_id = :b"),
                        {"b": belge_id}).scalar_one() == 0


def test_analiz_isci_ayrimi_metin_isini_almaz(conn, acik, depolama):
    belge_yukle(conn, depolama, dava_id=acik["dava"], kullanici_id=acik["kullanici"], orijinal_ad="a.pdf",
                veri=pdf_uret("Bekleyen metin cikarma"))
    # Yalnızca analiz alan işçi metin çıkarma görevine dokunmaz
    assert gorevi_isle(conn, depolama, ("analiz",)) is None
