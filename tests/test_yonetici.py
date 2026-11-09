"""Yönetici ekranı uçları ve geçici parola akışı. Oturum gerçek çerezle taşınır; veriler sentetiktir."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.kimlik import yonetici, yonetim
from app.main import app
from test_kimlik import PAROLA, web  # noqa: F401 (web bir fikstürdür)

YENI_PAROLA = "Baska-Sentetik-Parola-5821"   # e-posta adını ("yeni") içermemeli


@pytest.fixture
def buro(conn, dava):
    """Biri yönetici, biri avukat iki parolalı hesap."""
    yon = yonetim.kullanici_ekle(conn, buro_id=dava["buro"], ad_soyad="Av. Yönetici", e_posta="yon@ornek.test",
                                 rol="yonetici", parola=PAROLA)
    avk = yonetim.kullanici_ekle(conn, buro_id=dava["buro"], ad_soyad="Av. Avukat", e_posta="avk@ornek.test",
                                 rol="avukat", parola=PAROLA)
    return {"buro": dava["buro"], "yonetici": yon, "avukat": avk}


def _oturum(e_posta, parola=PAROLA):
    """Ayrı çerez kavanozuyla yeni istemci (fikstürdeki bağımlılık yönlendirmeleri geçerlidir)."""
    c = TestClient(app)
    assert c.post("/oturum/giris", json={"e_posta": e_posta, "parola": parola}).status_code == 200
    return c


def _denetim(conn, buro_id, eylem):
    return conn.execute(text("SELECT hedef_tur, ayrinti FROM denetim_kaydi WHERE buro_id = :b AND eylem = :e "
                             "ORDER BY id"), {"b": buro_id, "e": eylem}).all()


def test_yeni_hesap_gecici_parolayla_acilir_ilk_giriste_parola_degismeli(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    yanit = yon.post("/yonetim/kullanicilar", json={"ad_soyad": "Av. Yeni Kişi", "e_posta": "Yeni@Ornek.test",
                                                    "rol": "stajyer"})
    assert yanit.status_code == 201 and yanit.headers["cache-control"] == "no-store"
    gecici = yanit.json()["gecici_parola"]

    yeni = _oturum("yeni@ornek.test", gecici)
    assert yeni.get("/oturum/ben").json()["parola_degismeli"] is True
    # Parola değişene kadar hiçbir iş ucu açılmaz
    engel = yeni.get("/davalar")
    assert engel.status_code == 403 and "parolanızı değiştirmeniz" in engel.json()["detail"]

    assert yeni.post("/oturum/parola", json={"mevcut": "yanlis", "yeni": YENI_PAROLA}).status_code == 422
    assert yeni.post("/oturum/parola", json={"mevcut": gecici, "yeni": "kisa"}).status_code == 422
    assert yeni.post("/oturum/parola", json={"mevcut": gecici, "yeni": gecici}).status_code == 422
    assert yeni.post("/oturum/parola", json={"mevcut": gecici, "yeni": YENI_PAROLA}).status_code == 204
    # Aynı oturum açık kalır ve artık çalışır
    assert yeni.get("/oturum/ben").json()["parola_degismeli"] is False
    assert yeni.get("/davalar").status_code == 200
    assert _oturum("yeni@ornek.test", YENI_PAROLA)

    # Geçici parola hiçbir denetim kaydına yazılmaz
    tumu = json.dumps([list(map(str, s)) for s in conn.execute(text("SELECT ayrinti FROM denetim_kaydi "
                                                                    "WHERE buro_id = :b"), {"b": buro["buro"]})])
    assert gecici not in tumu
    assert [s.hedef_tur for s in _denetim(conn, buro["buro"], "olusturma")] == ["kullanici"]


def test_yonetici_olmayan_yonetim_uclarini_kullanamaz_ve_red_kaydedilir(conn, web, buro):
    avk = _oturum("avk@ornek.test")
    assert avk.get("/yonetim/kullanicilar").status_code == 403
    assert avk.post("/yonetim/kullanicilar", json={"ad_soyad": "X Y", "e_posta": "x@ornek.test",
                                                   "rol": "yonetici"}).status_code == 403
    assert avk.put("/yonetim/buro/analiz", json={"analiz_modeli": None}).status_code == 403
    redler = [s.ayrinti["istenen_eylem"] for s in _denetim(conn, buro["buro"], "erisim_reddi")]
    assert redler == ["goruntuleme", "olusturma", "guncelleme"]


def test_baska_buronun_kullanicisi_bulunamaz(conn, web, buro):
    diger_buro = conn.execute(text("INSERT INTO buro (ad) VALUES ('Diğer Büro') RETURNING id")).scalar_one()
    yabanci = yonetim.kullanici_ekle(conn, buro_id=str(diger_buro), ad_soyad="Av. Yabancı",
                                     e_posta="yabanci@ornek.test", rol="avukat", parola=PAROLA)
    yon = _oturum("yon@ornek.test")
    assert yon.patch(f"/yonetim/kullanicilar/{yabanci}", json={"aktif": False}).status_code == 404
    assert yon.post(f"/yonetim/kullanicilar/{yabanci}/gecici-parola").status_code == 404
    assert {k["e_posta"] for k in yon.get("/yonetim/kullanicilar").json()["kullanicilar"]} == {
        "yon@ornek.test", "avk@ornek.test", "deneme@ornek.test"}


def test_yonetici_kendini_dusuremez_buro_yoneticisiz_kalamaz(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    for govde in ({"rol": "avukat"}, {"aktif": False}):
        yanit = yon.patch(f"/yonetim/kullanicilar/{buro['yonetici']}", json=govde)
        assert yanit.status_code == 422 and "Kendi" in yanit.json()["detail"]
    # İkinci yönetici: onu düşürmek serbest, oturumu kapanır
    ikinci = yonetim.kullanici_ekle(conn, buro_id=buro["buro"], ad_soyad="Av. İkinci", e_posta="iki@ornek.test",
                                    rol="yonetici", parola=PAROLA)
    iki = _oturum("iki@ornek.test")
    assert yon.patch(f"/yonetim/kullanicilar/{ikinci}", json={"rol": "avukat"}).status_code == 204
    assert iki.get("/davalar").status_code == 401
    degisim = _denetim(conn, buro["buro"], "erisim_degisikligi")[-1].ayrinti
    assert degisim["rol"] == ["yonetici", "avukat"] and degisim["kapanan_oturum"] == 1


def test_pasiflestirme_oturumu_kapatir_gecici_parola_kilidi_acar(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    avk = _oturum("avk@ornek.test")
    assert yon.patch(f"/yonetim/kullanicilar/{buro['avukat']}", json={"aktif": False}).status_code == 204
    assert avk.get("/davalar").status_code == 401
    assert TestClient(app).post("/oturum/giris", json={"e_posta": "avk@ornek.test",
                                                       "parola": PAROLA}).status_code == 401
    assert yon.patch(f"/yonetim/kullanicilar/{buro['avukat']}", json={"aktif": True}).status_code == 204

    conn.execute(text("UPDATE kullanici SET basarisiz_giris = 5, kilit_bitis = now() + interval '1 hour' "
                      "WHERE id = :k"), {"k": buro["avukat"]})
    satir = next(k for k in yon.get("/yonetim/kullanicilar").json()["kullanicilar"] if k["e_posta"] == "avk@ornek.test")
    assert satir["kilitli"] is True
    yanit = yon.post(f"/yonetim/kullanicilar/{buro['avukat']}/gecici-parola")
    assert yanit.status_code == 200
    yeni = _oturum("avk@ornek.test", yanit.json()["gecici_parola"])
    assert yeni.get("/oturum/ben").json()["parola_degismeli"] is True
    assert _denetim(conn, buro["buro"], "guncelleme")[-1].ayrinti["islem"] == "gecici_parola"


def test_ayni_e_posta_ikinci_kez_acilamaz(web, buro):
    yon = _oturum("yon@ornek.test")
    yanit = yon.post("/yonetim/kullanicilar", json={"ad_soyad": "Av. Kopya", "e_posta": "AVK@ornek.test",
                                                    "rol": "avukat"})
    assert yanit.status_code == 409


def test_analiz_yalnizca_kurulu_yerel_modelle_acilir(conn, web, buro, monkeypatch):
    monkeypatch.setattr(yonetici, "yerel_modeller", lambda: ["qwen3.5:4b"])
    yon = _oturum("yon@ornek.test")
    assert yon.get("/yonetim/buro").json()["yerel_modeller"] == ["ollama:qwen3.5:4b"]
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": "bulut:herhangi"}).status_code == 422
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": "ollama:kurulu-degil"}).status_code == 422
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": "ollama:qwen3.5:4b"}).status_code == 204
    assert yon.get("/yonetim/buro").json()["analiz_modeli"] == "ollama:qwen3.5:4b"
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": None}).status_code == 204
    assert [s.ayrinti["analiz_modeli"] for s in _denetim(conn, buro["buro"], "guncelleme")] == [
        [None, "ollama:qwen3.5:4b"], ["ollama:qwen3.5:4b", None]]

    monkeypatch.setattr(yonetici, "yerel_modeller", lambda: None)
    assert yon.get("/yonetim/buro").json()["yerel_modeller"] is None
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": "ollama:qwen3.5:4b"}).status_code == 503
    # Kapatmak her zaman mümkün
    assert yon.put("/yonetim/buro/analiz", json={"analiz_modeli": None}).status_code == 204


# --- Düzenleme: kullanıcı adı/e-postası ve büro adı ---------------------

def test_yonetici_ad_ve_e_posta_degistirir_kisi_yeni_e_postayla_girer(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    avk = _oturum("avk@ornek.test")
    yanit = yon.patch(f"/yonetim/kullanicilar/{buro['avukat']}",
                      json={"ad_soyad": " Av. Yeni Ad ", "e_posta": "Yeni.Adres@Ornek.test"})
    assert yanit.status_code == 204, yanit.text
    satir = conn.execute(text("SELECT ad_soyad, e_posta FROM kullanici WHERE id = :k"), {"k": buro["avukat"]}).one()
    assert tuple(satir) == ("Av. Yeni Ad", "yeni.adres@ornek.test")
    # Eski oturum kapandı; eski e-postayla giriş olmaz, yenisiyle olur
    assert avk.get("/oturum/ben").status_code == 401
    assert TestClient(app).post("/oturum/giris", json={"e_posta": "avk@ornek.test", "parola": PAROLA}).status_code == 401
    _oturum("yeni.adres@ornek.test")
    ((hedef_tur, ayrinti),) = _denetim(conn, buro["buro"], "guncelleme")
    assert hedef_tur == "kullanici"
    assert ayrinti["ad_soyad"] == ["Av. Avukat", "Av. Yeni Ad"]
    assert ayrinti["e_posta"] == ["avk@ornek.test", "yeni.adres@ornek.test"] and ayrinti["kapanan_oturum"] >= 1


def test_e_posta_baskasininkiyle_cakisamaz_yonetici_kendi_e_postasini_degistirince_oturumu_surer(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    assert yon.patch(f"/yonetim/kullanicilar/{buro['avukat']}", json={"e_posta": "YON@ornek.test"}).status_code == 409
    assert yon.patch(f"/yonetim/kullanicilar/{buro['yonetici']}", json={"e_posta": "yon2@ornek.test"}).status_code == 204
    assert yon.get("/oturum/ben").json()["e_posta"] == "yon2@ornek.test"
    # Avukat başkasının bilgisini değiştiremez
    avk = _oturum("avk@ornek.test")
    assert avk.patch(f"/yonetim/kullanicilar/{buro['yonetici']}", json={"ad_soyad": "Olmaz"}).status_code == 403


def test_buro_adi_degisir_denetime_yazilir(conn, web, buro):
    yon = _oturum("yon@ornek.test")
    assert yon.put("/yonetim/buro/ad", json={"ad": "  Yeni   Büro Adı "}).status_code == 204
    assert yon.get("/yonetim/buro").json()["ad"] == "Yeni Büro Adı"
    assert yon.get("/oturum/ben").json()["buro_adi"] == "Yeni Büro Adı"
    ((hedef_tur, ayrinti),) = _denetim(conn, buro["buro"], "guncelleme")
    assert hedef_tur == "buro" and ayrinti == {"ad": ["Örnek Hukuk Bürosu", "Yeni Büro Adı"]}
    assert yon.put("/yonetim/buro/ad", json={"ad": "   "}).status_code == 422
    assert _oturum("avk@ornek.test").put("/yonetim/buro/ad", json={"ad": "Olmaz"}).status_code == 403
