"""Belge listeleme ve görüntüleme uçlarının testleri. Tüm belgeler sentetiktir."""

import uuid
from urllib.parse import quote

import pytest
from sqlalchemy import text

from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle
from conftest import ekle
from test_belge import pdf_uret


def _yukle(conn, dava, depolama, veri, ad="dilekce.pdf"):
    return belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                       orijinal_ad=ad, veri=veri)["id"]


def _al(istemci, yol, kullanici, **kw):
    return istemci.get(yol, headers={"X-Kullanici-Id": str(kullanici)}, **kw)


def _denetim(conn, eylem, hedef_tur, hedef_id):
    return conn.execute(
        text("SELECT count(*) FROM denetim_kaydi WHERE eylem = :e AND hedef_tur = :t AND hedef_id = :h"),
        {"e": eylem, "t": hedef_tur, "h": hedef_id},
    ).scalar_one()


def _yabanci_kullanici(conn):
    diger_buro = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    return ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yabancı', 'yabanci@ornek.test', 'yonetici')",
        b=diger_buro,
    )


def _yetkisiz_avukat(conn, dava):
    return ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yetkisiz', 'yetkisiz@ornek.test', 'avukat')",
        b=dava["buro"],
    )


def _ocr_sayfasi_yap(conn, belge_id, sayfa_no, guven):
    conn.execute(
        text(
            "UPDATE belge_sayfa SET metin_kaynagi = 'ocr', ocr_guven_skoru = :g "
            "WHERE belge_id = :b AND sayfa_no = :n"
        ),
        {"b": belge_id, "n": sayfa_no, "g": guven},
    )


# --- Listeleme -------------------------------------------

def test_dava_belgeleri_listelenir_ve_denetime_yazilir(conn, dava, depolama, istemci):
    birinci = _yukle(conn, dava, depolama, pdf_uret("Birinci sayfa", "Ikinci sayfa"), "dilekce.pdf")
    gorevi_isle(conn, depolama)
    _ocr_sayfasi_yap(conn, birinci, 2, 0.81)
    ikinci = _yukle(conn, dava, depolama, pdf_uret("Cevap"), "cevap.pdf")

    yanit = _al(istemci, f"/davalar/{dava['dava']}/belgeler", dava["kullanici"])
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["toplam"] == 2
    belgeler = {b["id"]: b for b in govde["belgeler"]}
    assert set(belgeler) == {str(birinci), str(ikinci)}
    assert belgeler[str(birinci)]["sayfa_sayisi"] == 2
    assert belgeler[str(birinci)]["ocr_sayfa_sayisi"] == 1
    assert belgeler[str(birinci)]["uyarili_sayfa_sayisi"] == 1
    assert belgeler[str(ikinci)]["durum"] == "yuklendi"
    # İç depolama anahtarı dışarı verilmez
    assert all("depolama_anahtari" not in b for b in govde["belgeler"])
    assert _denetim(conn, "goruntuleme", "belge_listesi", dava["dava"]) == 1


def test_tekrarlanan_goruntuleme_tek_kayitta_birlesir_indirme_birlesmez(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Birlestirme"))
    for _ in range(3):  # arayüzün otomatik yenilemesi gibi
        assert _al(istemci, f"/davalar/{dava['dava']}/belgeler", dava["kullanici"]).status_code == 200
        assert _al(istemci, f"/belgeler/{belge_id}/dosya", dava["kullanici"]).status_code == 200
    assert _denetim(conn, "goruntuleme", "belge_listesi", dava["dava"]) == 1
    assert _denetim(conn, "disa_aktarim", "belge", belge_id) == 3
    # Başka bir kullanıcının görüntülemesi ayrıca kaydedilir
    yonetici = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                          "VALUES (:b, 'Yönetici', 'yonetici@ornek.test', 'yonetici')", b=dava["buro"])
    _al(istemci, f"/davalar/{dava['dava']}/belgeler", yonetici)
    assert _denetim(conn, "goruntuleme", "belge_listesi", dava["dava"]) == 2
    # Süre dolunca yeni kayıt açılır
    conn.execute(text("UPDATE denetim_kaydi SET zaman = now() - interval '6 minutes' WHERE eylem = 'goruntuleme'"))
    _al(istemci, f"/davalar/{dava['dava']}/belgeler", dava["kullanici"])
    assert _denetim(conn, "goruntuleme", "belge_listesi", dava["dava"]) == 3


def test_listeleme_sayfalanir(conn, dava, depolama, istemci):
    for i in range(3):
        _yukle(conn, dava, depolama, pdf_uret(f"Belge {i}"), f"belge{i}.pdf")
    yol = f"/davalar/{dava['dava']}/belgeler"
    sayfa1 = _al(istemci, yol, dava["kullanici"], params={"limit": 2}).json()
    sayfa2 = _al(istemci, yol, dava["kullanici"], params={"limit": 2, "offset": 2}).json()
    assert (sayfa1["toplam"], len(sayfa1["belgeler"]), len(sayfa2["belgeler"])) == (3, 2, 1)
    kimlikler = [b["id"] for b in sayfa1["belgeler"] + sayfa2["belgeler"]]
    assert len(set(kimlikler)) == 3
    assert _al(istemci, yol, dava["kullanici"], params={"limit": 500}).status_code == 422


def test_listelemede_erisim_denetlenir_ve_basarisiz_deneme_kaydedilmez(conn, dava, istemci):
    yol = f"/davalar/{dava['dava']}/belgeler"
    assert _al(istemci, yol, _yetkisiz_avukat(conn, dava)).status_code == 403
    assert _al(istemci, yol, _yabanci_kullanici(conn)).status_code == 404
    assert _al(istemci, f"/davalar/{uuid.uuid4()}/belgeler", dava["kullanici"]).status_code == 404
    assert _denetim(conn, "goruntuleme", "belge_listesi", dava["dava"]) == 0


# --- Ayrıntı ---------------------------------------------

def test_belge_ayrintisi_sayfa_ve_gorev_durumunu_gosterir(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Birinci", "Ikinci"))
    gorevi_isle(conn, depolama)
    _ocr_sayfasi_yap(conn, belge_id, 2, 0.97)

    yanit = _al(istemci, f"/belgeler/{belge_id}", dava["kullanici"])
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert govde["durum"] == "hazir" and govde["sayfa_sayisi"] == 2
    assert "depolama_anahtari" not in govde
    assert [(s["sayfa_no"], s["metin_kaynagi"], s["asliyla_karsilastir"]) for s in govde["sayfalar"]] == [
        (1, "dogrudan", False), (2, "ocr", False),
    ]
    assert [(g["adim"], g["durum"]) for g in govde["gorevler"]] == [("metin_cikarma", "tamam")]
    assert _denetim(conn, "goruntuleme", "belge", belge_id) == 1


def test_baska_buronun_belgesi_bulunamadi_doner(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Gizli"))
    yabanci = _yabanci_kullanici(conn)
    for yol in (f"/belgeler/{belge_id}", f"/belgeler/{belge_id}/sayfalar/1", f"/belgeler/{belge_id}/dosya"):
        yanit = _al(istemci, yol, yabanci)
        assert yanit.status_code == 404, yol
        assert yanit.json()["detail"] == "Belge bulunamadı."
    assert _al(istemci, f"/belgeler/{uuid.uuid4()}", dava["kullanici"]).status_code == 404
    assert _al(istemci, f"/belgeler/{belge_id}", _yetkisiz_avukat(conn, dava)).status_code == 403


# --- Sayfa metni -----------------------------------------

def test_sayfa_metni_doner(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Sentetik dilekce metni"))
    gorevi_isle(conn, depolama)
    yanit = _al(istemci, f"/belgeler/{belge_id}/sayfalar/1", dava["kullanici"])
    assert yanit.status_code == 200, yanit.text
    govde = yanit.json()
    assert "Sentetik dilekce" in govde["metin"]
    assert (govde["metin_kaynagi"], govde["asliyla_karsilastir"], govde["uyari"]) == ("dogrudan", False, None)
    sayfa_id = conn.execute(
        text("SELECT id FROM belge_sayfa WHERE belge_id = :b AND sayfa_no = 1"), {"b": belge_id}
    ).scalar_one()
    assert _denetim(conn, "goruntuleme", "belge_sayfa", sayfa_id) == 1


@pytest.mark.parametrize("guven, uyari", [(0.81, True), (None, True), (0.93, False), (0.97, False)])
def test_ocr_sayfasinda_dusuk_guven_uyarisi(conn, dava, depolama, istemci, guven, uyari):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Taranmis gibi"))
    gorevi_isle(conn, depolama)
    _ocr_sayfasi_yap(conn, belge_id, 1, guven)
    govde = _al(istemci, f"/belgeler/{belge_id}/sayfalar/1", dava["kullanici"]).json()
    assert govde["asliyla_karsilastir"] is uyari
    assert (govde["uyari"] is not None) is uyari


def test_olmayan_sayfa(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("Tek sayfa"))
    gorevi_isle(conn, depolama)
    assert _al(istemci, f"/belgeler/{belge_id}/sayfalar/2", dava["kullanici"]).status_code == 404
    assert _al(istemci, f"/belgeler/{belge_id}/sayfalar/0", dava["kullanici"]).status_code == 422


# --- Orijinal dosya --------------------------------------

def test_orijinal_dosya_indirilir(conn, dava, depolama, istemci):
    veri = pdf_uret("Bilirkisi raporu")
    ad = "Bilirkişi raporu – Çağlar Gıda.pdf"
    belge_id = _yukle(conn, dava, depolama, veri, ad)

    yanit = _al(istemci, f"/belgeler/{belge_id}/dosya", dava["kullanici"])
    assert yanit.status_code == 200
    assert yanit.content == veri
    assert yanit.headers["content-type"] == "application/pdf"
    assert yanit.headers["cache-control"] == "no-store"
    assert yanit.headers["x-content-type-options"] == "nosniff"
    baslik = yanit.headers["content-disposition"]
    assert baslik.startswith("attachment;")
    assert f"filename*=UTF-8''{quote(ad, safe='')}" in baslik
    assert 'filename="Bilirkisi raporu  Caglar Gida.pdf"' in baslik
    assert _denetim(conn, "disa_aktarim", "belge", belge_id) == 1


def test_dosya_adi_baslik_enjeksiyonuna_yol_acmaz(conn, dava, depolama, istemci):
    belge_id = _yukle(conn, dava, depolama, pdf_uret("x"), 'kotu"\r\nX-Kotu: 1\r\n.pdf')
    yanit = _al(istemci, f"/belgeler/{belge_id}/dosya", dava["kullanici"])
    assert yanit.status_code == 200
    assert "x-kotu" not in yanit.headers
    baslik = yanit.headers["content-disposition"]
    assert "\r" not in baslik and "\n" not in baslik
    assert 'filename="kotuX-Kotu: 1.pdf"' in baslik
