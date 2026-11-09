"""Denetim kaydı ekranı: süzgeçler, sayfalama, özet, CSV ve büro sınırı. Veriler sentetiktir."""

import csv
import io
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text

from app.kimlik import yonetim
from app.main import app
from test_kimlik import PAROLA, web  # noqa: F401 (web bir fikstürdür)
from test_yonetici import _oturum, buro  # noqa: F401 (buro bir fikstürdür)


def _kayitlar(istemci, **suzgec):
    yanit = istemci.get("/yonetim/denetim", params=suzgec)
    assert yanit.status_code == 200, yanit.text
    return yanit.json()


def test_liste_hedef_adlarini_cozer_suzer_ve_sayfalar(conn, web, buro, dava):
    yon = _oturum("yon@ornek.test")
    avk = _oturum("avk@ornek.test")
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'sorumlu')"),
                 {"d": dava["dava"], "k": buro["avukat"]})
    assert avk.get(f"/davalar/{dava['dava']}").status_code == 200

    tumu = _kayitlar(yon)["kayitlar"]
    goruntuleme = next(k for k in tumu if k["eylem"] == "goruntuleme" and k["hedef_tur"] == "dava_dosyasi")
    assert goruntuleme["kullanici_adi"] == "Av. Avukat" and goruntuleme["hedef_adi"] == "2026/1 · Sentetik Dava"
    assert goruntuleme["hedef_dava_id"] == str(dava["dava"])
    girisler = _kayitlar(yon, eylem="giris")["kayitlar"]
    assert {k["kullanici_adi"] for k in girisler} == {"Av. Yönetici", "Av. Avukat"}
    assert {k["eylem"] for k in _kayitlar(yon, kullanici=str(buro["avukat"]))["kayitlar"]} == {"giris", "goruntuleme"}

    # Sayfalama: önceki sayfanın son kimliğinden devam, çakışma yok
    s1 = _kayitlar(yon, limit=2)
    s2 = _kayitlar(yon, limit=2, once=s1["sonraki"])
    assert s1["sonraki"] is not None and not {k["id"] for k in s1["kayitlar"]} & {k["id"] for k in s2["kayitlar"]}
    # Tarih süzgeci: dünle biten aralıkta bugünkü kayıt yok
    assert _kayitlar(yon, bitis=(date.today() - timedelta(days=1)).isoformat())["kayitlar"] == []
    assert yon.get("/yonetim/denetim", params={"eylem": "uydurma"}).status_code == 422
    # Ekranı görüntülemek de denetime yazılır
    assert any(k["hedef_tur"] == "denetim_kaydi" for k in _kayitlar(yon, eylem="goruntuleme")["kayitlar"])


def test_baska_buronun_dosyasinin_adi_gosterilmez(conn, web, buro):
    diger_buro = conn.execute(text("INSERT INTO buro (ad) VALUES ('Diğer Büro') RETURNING id")).scalar_one()
    diger_kullanici = yonetim.kullanici_ekle(conn, buro_id=str(diger_buro), ad_soyad="Av. Yabancı",
                                             e_posta="yabanci@ornek.test", rol="avukat", parola=None)
    muvekkil = conn.execute(text("INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'gercek_kisi', "
                                 "'Gizli Müvekkil') RETURNING id"), {"b": diger_buro}).scalar_one()
    gizli_dava = conn.execute(text(
        "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, olusturan_kullanici_id) "
        "VALUES (:b, :m, '2026/999', 'Gizli Dava Başlığı', :k) RETURNING id"),
        {"b": diger_buro, "m": muvekkil, "k": diger_kullanici}).scalar_one()

    avk = _oturum("avk@ornek.test")
    assert avk.get(f"/davalar/{gizli_dava}").status_code == 404
    yon = _oturum("yon@ornek.test")
    (red,) = _kayitlar(yon, eylem="erisim_reddi")["kayitlar"]
    assert red["hedef_id"] == str(gizli_dava) and red["hedef_adi"] is None and red["hedef_dava_id"] is None
    csv_metni = yon.get("/yonetim/denetim/disa-aktar").text
    assert "Gizli Dava" not in csv_metni and "2026/999" not in csv_metni


def test_yonetici_olmayan_denetim_kaydini_goremez(web, buro):
    avk = _oturum("avk@ornek.test")
    for yol in ("/yonetim/denetim", "/yonetim/denetim/ozet", "/yonetim/denetim/disa-aktar"):
        assert avk.get(yol).status_code == 403
    assert web.get("/yonetim/denetim", params={"eylem": "uydurma"}).status_code == 401


def test_ozet_reddedilenleri_ve_kilitlenen_hesaplari_gosterir(conn, web, buro):
    avk = _oturum("avk@ornek.test")
    for _ in range(2):
        assert avk.get("/yonetim/kullanicilar").status_code == 403
    for _ in range(5):
        TestClient(app).post("/oturum/giris", json={"e_posta": "avk@ornek.test", "parola": "yanlis-parola-xx"})
    yon = _oturum("yon@ornek.test")
    o = yon.get("/yonetim/denetim/ozet").json()
    assert o["reddedilen_kullanicilar"][0]["ad_soyad"] == "Av. Avukat"
    assert o["reddedilen_kullanicilar"][0]["sayi"] == 2
    assert [k["ad_soyad"] for k in o["kilitlenen_hesaplar"]] == ["Av. Avukat"]
    assert o["eylemler"]["giris_basarisiz"] == 5


def test_csv_excel_uyumlu_formul_enjeksiyonu_etkisiz_ve_denetime_yazilir(conn, web, buro):
    yonetim.kullanici_ekle(conn, buro_id=buro["buro"], ad_soyad="=HYPERLINK(\"http://x\")",
                           e_posta="formul@ornek.test", rol="stajyer", parola=PAROLA)
    _oturum("formul@ornek.test")
    yon = _oturum("yon@ornek.test")
    yanit = yon.get("/yonetim/denetim/disa-aktar", params={"eylem": "giris"})
    assert yanit.status_code == 200 and yanit.headers["content-type"].startswith("text/csv")
    assert "attachment" in yanit.headers["content-disposition"]
    assert yanit.content.startswith("﻿".encode())
    satirlar = list(csv.reader(io.StringIO(yanit.text.lstrip("﻿")), delimiter=";"))
    assert satirlar[0][:3] == ["Kayıt no", "Zaman", "Kullanıcı"]
    assert "'=HYPERLINK(\"http://x\")" in [s[2] for s in satirlar[1:]]
    aktarim = conn.execute(text("SELECT ayrinti FROM denetim_kaydi WHERE buro_id = :b AND eylem = 'disa_aktarim'"),
                           {"b": buro["buro"]}).scalar_one()
    assert aktarim["satir"] == len(satirlar) - 1 and aktarim["suzgec"]["eylemler"] == ["giris"]
