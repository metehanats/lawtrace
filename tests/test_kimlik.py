"""Kimlik doğrulama testleri: giriş, oturum, kilitleme, çıkış ve yönetim komutları.

Bu testlerde oturum gerçekten çerezle taşınır; conftest'teki başlık kısayolu kullanılmaz.
Parolalar yalnızca bu testlere ait sentetik değerlerdir.
"""

import hashlib
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import ayarlar
from app.belge.api import ayri_islem, depolama_al
from app.db import baglanti
from app.kimlik import oturum, parola as parola_mod, yonetim
from app.main import app

PAROLA = "Sentetik-Test-Parolasi-7391"


@pytest.fixture
def web(conn, depolama, monkeypatch):
    """Gerçek oturum bağımlılığıyla çalışan istemci (yalnızca bağlantı test bağlantısına yönlenir)."""
    # Test istemcisi http üzerinden konuşur; Secure çerez http'de gönderilmez
    monkeypatch.setattr(ayarlar, "OTURUM_COOKIE_GUVENLI", False)

    @contextmanager
    def kayit_noktasi():
        with conn.begin_nested():
            yield conn

    app.dependency_overrides[baglanti] = lambda: conn
    app.dependency_overrides[depolama_al] = lambda: depolama
    app.dependency_overrides[ayri_islem] = lambda: kayit_noktasi
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def hesap(conn, dava):
    """Parolası olan, dava dosyasına erişimi olan sentetik avukat."""
    kimlik = yonetim.kullanici_ekle(conn, buro_id=dava["buro"], ad_soyad="Av. Giriş Deneme",
                                    e_posta="Giris.Deneme@ornek.test", rol="avukat", parola=PAROLA)
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'sorumlu')"),
                 {"d": dava["dava"], "k": kimlik})
    return {"id": kimlik, "e_posta": "giris.deneme@ornek.test", **dava}


def _giris(web, e_posta, parola=PAROLA):
    return web.post("/oturum/giris", json={"e_posta": e_posta, "parola": parola})


def _denetim(conn, eylem, kullanici_id):
    return conn.execute(
        text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = :e AND kullanici_id = :k ORDER BY id"),
        {"e": eylem, "k": kullanici_id},
    ).scalars().all()


def _kullanici(conn, kimlik):
    return conn.execute(
        text("SELECT basarisiz_giris, kilit_bitis > now() AS kilitli, son_giris FROM kullanici WHERE id = :k"),
        {"k": kimlik},
    ).one()


# --- Giriş -----------------------------------------------

def test_basarili_giris_cerez_verir_ve_oturum_acar(conn, web, hesap):
    yanit = _giris(web, hesap["e_posta"])
    assert yanit.status_code == 200, yanit.text
    assert yanit.json()["kullanici"]["e_posta"] == hesap["e_posta"]
    assert yanit.headers["cache-control"] == "no-store"
    cerez = yanit.headers["set-cookie"].lower()
    assert "httponly" in cerez and "samesite=lax" in cerez and "path=/" in cerez
    # Belirteç yanıt gövdesinde dönmez
    belirtec = web.cookies.get(ayarlar.OTURUM_COOKIE_ADI)
    assert belirtec and belirtec not in yanit.text

    ben = web.get("/oturum/ben")
    assert ben.status_code == 200 and ben.json()["id"] == str(hesap["id"])
    assert _kullanici(conn, hesap["id"]).son_giris is not None
    assert len(_denetim(conn, "giris", hesap["id"])) == 1


def test_belirtec_veritabaninda_yalnizca_ozet_olarak_tutulur(conn, web, hesap):
    _giris(web, hesap["e_posta"])
    belirtec = web.cookies.get(ayarlar.OTURUM_COOKIE_ADI)
    (ozet,) = conn.execute(text("SELECT belirtec_ozet FROM oturum WHERE kullanici_id = :k"),
                           {"k": hesap["id"]}).one()
    assert ozet == hashlib.sha256(belirtec.encode()).hexdigest()
    assert belirtec not in str(conn.execute(text("SELECT * FROM oturum")).all())


def test_e_posta_buyuk_kucuk_harf_duyarsiz(web, hesap):
    assert _giris(web, "  GIRIS.Deneme@ORNEK.test ").status_code == 200


def test_parola_veritabaninda_argon2_ozetiyle_tutulur(conn, hesap):
    ozet = conn.execute(text("SELECT parola_ozet FROM kullanici WHERE id = :k"), {"k": hesap["id"]}).scalar_one()
    assert ozet.startswith("$argon2id$") and PAROLA not in ozet


# --- Başarısız giriş -------------------------------------

def test_yanlis_parola_genel_mesaj_ve_sayac(conn, web, hesap):
    yanit = _giris(web, hesap["e_posta"], "Yanlis-Parola-12345")
    assert (yanit.status_code, yanit.json()["detail"]) == (401, oturum.GENEL_HATA)
    assert ayarlar.OTURUM_COOKIE_ADI not in web.cookies
    assert _kullanici(conn, hesap["id"]).basarisiz_giris == 1
    assert _denetim(conn, "giris_basarisiz", hesap["id"]) == [{"neden": "yanlis_parola"}]


def test_bilinmeyen_e_posta_ayni_mesaji_alir_ve_parola_yine_dogrulanir(web, hesap, monkeypatch):
    dogrulamalar = []
    asil = parola_mod.dogrula
    monkeypatch.setattr(parola_mod, "dogrula", lambda o, p: dogrulamalar.append(o) or asil(o, p))
    yanit = _giris(web, "olmayan@ornek.test")
    assert (yanit.status_code, yanit.json()["detail"]) == (401, oturum.GENEL_HATA)
    # Yanıt süresi kayıtlı hesaplarla aynı olsun diye sahte özet doğrulanır
    assert dogrulamalar == [None]


def test_bes_hatali_giristen_sonra_hesap_kilitlenir(conn, web, hesap):
    for _ in range(ayarlar.GIRIS_KILIT_ESIGI):
        assert _giris(web, hesap["e_posta"], "Yanlis-Parola-12345").status_code == 401
    assert _kullanici(conn, hesap["id"]).kilitli
    assert _denetim(conn, "giris_basarisiz", hesap["id"])[-1] == {"neden": "yanlis_parola", "hesap_kilitlendi": True}

    # Kilitliyken doğru parola da reddedilir ve mesaj değişmez
    yanit = _giris(web, hesap["e_posta"])
    assert (yanit.status_code, yanit.json()["detail"]) == (401, oturum.GENEL_HATA)
    assert _denetim(conn, "giris_basarisiz", hesap["id"])[-1] == {"neden": "kilitli"}

    # Kilit süresi dolunca giriş yapılabilir
    conn.execute(text("UPDATE kullanici SET kilit_bitis = now() - interval '1 minute' WHERE id = :k"),
                 {"k": hesap["id"]})
    assert _giris(web, hesap["e_posta"]).status_code == 200
    assert _kullanici(conn, hesap["id"]).basarisiz_giris == 0


def test_pasif_ve_parolasiz_hesap_giremez(conn, web, hesap, dava):
    conn.execute(text("UPDATE kullanici SET aktif = false WHERE id = :k"), {"k": hesap["id"]})
    assert _giris(web, hesap["e_posta"]).status_code == 401
    assert _denetim(conn, "giris_basarisiz", hesap["id"]) == [{"neden": "pasif_hesap"}]

    parolasiz = yonetim.kullanici_ekle(conn, buro_id=dava["buro"], ad_soyad="Av. Parolasız",
                                       e_posta="parolasiz@ornek.test", rol="avukat", parola=None)
    assert _giris(web, "parolasiz@ornek.test", "Herhangi-Bir-Parola").status_code == 401
    assert _denetim(conn, "giris_basarisiz", parolasiz) == [{"neden": "parola_tanimsiz"}]


def test_asiri_uzun_parola_reddedilir(web, hesap):
    assert _giris(web, hesap["e_posta"], "x" * 5000).status_code == 422


# --- Oturum ----------------------------------------------

def test_oturum_olmadan_belge_uclarina_erisilemez(web, hesap):
    for yol in (f"/davalar/{hesap['dava']}/belgeler", "/oturum/ben"):
        yanit = web.get(yol)
        assert yanit.status_code == 401, yol
    # Eski geçici başlık artık işe yaramaz
    assert web.get(f"/davalar/{hesap['dava']}/belgeler",
                   headers={"X-Kullanici-Id": str(hesap["id"])}).status_code == 401


def test_giris_sonrasi_belge_listesi_acilir(web, hesap):
    _giris(web, hesap["e_posta"])
    yanit = web.get(f"/davalar/{hesap['dava']}/belgeler")
    assert yanit.status_code == 200, yanit.text


def test_sahte_belirtec_reddedilir(web, hesap):
    web.cookies.set(ayarlar.OTURUM_COOKIE_ADI, "uydurma-belirtec")
    assert web.get("/oturum/ben").status_code == 401


@pytest.mark.parametrize("guncelleme", [
    "bitis = now() - interval '1 second'",          # en uzun süre doldu
    "son_kullanim = now() - interval '61 minutes'",  # boşta kaldı
    "iptal = now()",                                 # kapatıldı
])
def test_gecersiz_oturum_reddedilir(conn, web, hesap, guncelleme):
    _giris(web, hesap["e_posta"])
    conn.execute(text(f"UPDATE oturum SET {guncelleme} WHERE kullanici_id = :k"), {"k": hesap["id"]})
    assert web.get("/oturum/ben").status_code == 401


def test_cikis_oturumu_kapatir(conn, web, hesap):
    _giris(web, hesap["e_posta"])
    belirtec = web.cookies.get(ayarlar.OTURUM_COOKIE_ADI)
    yanit = web.post("/oturum/cikis")
    assert yanit.status_code == 204
    assert ayarlar.OTURUM_COOKIE_ADI not in web.cookies
    # Belirteç ele geçirilmiş olsa bile artık işe yaramaz
    web.cookies.set(ayarlar.OTURUM_COOKIE_ADI, belirtec)
    assert web.get("/oturum/ben").status_code == 401
    assert len(_denetim(conn, "cikis", hesap["id"])) == 1


# --- Yönetim komutları -----------------------------------

def test_zayif_parola_kabul_edilmez(conn, dava):
    for zayif in ("kisa", "aaaaaaaaaaaaaaaa", " bosluklu-parola-1234", "zayif.kullanici-2026!"):
        with pytest.raises(yonetim.YonetimHatasi):
            yonetim.kullanici_ekle(conn, buro_id=dava["buro"], ad_soyad="Av. Zayıf",
                                   e_posta="zayif.kullanici@ornek.test", rol="avukat", parola=zayif)


def test_parola_degisince_acik_oturumlar_kapanir(conn, web, hesap):
    _giris(web, hesap["e_posta"])
    assert yonetim.parola_belirle(conn, hesap["e_posta"], "Yeni-Sentetik-Parola-5521") == 1
    assert web.get("/oturum/ben").status_code == 401
    assert _giris(web, hesap["e_posta"]).status_code == 401
    assert _giris(web, hesap["e_posta"], "Yeni-Sentetik-Parola-5521").status_code == 200


def test_pasiflestirilen_hesabin_oturumu_kapanir(conn, web, hesap):
    _giris(web, hesap["e_posta"])
    yonetim.pasiflestir(conn, hesap["e_posta"])
    assert web.get("/oturum/ben").status_code == 401


def test_kilit_ac(conn, web, hesap):
    for _ in range(ayarlar.GIRIS_KILIT_ESIGI):
        _giris(web, hesap["e_posta"], "Yanlis-Parola-12345")
    yonetim.kilit_ac(conn, hesap["e_posta"])
    assert _giris(web, hesap["e_posta"]).status_code == 200


# --- Gerçek işlemlerle: başarısız giriş sayacı kalıcı olmalı -------------------

def test_basarisiz_giris_sayaci_istek_sonrasi_kalicidir(engine, monkeypatch):
    """İstek bağlantısı gerçek: 401 yanıtında da sayaç ve denetim kaydı onaylanmalı.

    (Hata istisnayla dönseydi işlem geri alınır, sayaç hiç artmaz ve kilit çalışmazdı.)
    """
    monkeypatch.setattr(ayarlar, "OTURUM_COOKIE_GUVENLI", False)
    with engine.begin() as c:
        buro = str(c.execute(text("INSERT INTO buro (ad) VALUES ('Kalıcı Giriş Bürosu') RETURNING id")).scalar_one())
        kimlik = yonetim.kullanici_ekle(c, buro_id=buro, ad_soyad="Av. Kalıcı", e_posta=f"kalici-{buro}@ornek.test",
                                        rol="avukat", parola=PAROLA)
    try:
        istemci = TestClient(app)
        for _ in range(2):
            assert _giris(istemci, f"kalici-{buro}@ornek.test", "Yanlis-Parola-12345").status_code == 401
        with engine.connect() as c:
            assert _kullanici(c, kimlik).basarisiz_giris == 2
            assert len(_denetim(c, "giris_basarisiz", kimlik)) == 2
    finally:
        with engine.begin() as c:
            for tablo in ("denetim_kaydi", "kullanici"):
                c.execute(text(f"DELETE FROM {tablo} WHERE buro_id = :b"), {"b": buro})
            c.execute(text("DELETE FROM buro WHERE id = :b"), {"b": buro})


def test_parola_degisiminde_yanlis_mevcut_parola_sayilir_kilitler_ve_kalicidir(engine, monkeypatch):
    """Oturumu ele geçiren biri parola değiştirme ekranında sınırsız tahmin yapamamalı.

    İstek bağlantısı gerçek: hatalı denemeler (422) ve kilit (401) yanıtında da sayaç onaylanmalı.
    """
    monkeypatch.setattr(ayarlar, "OTURUM_COOKIE_GUVENLI", False)
    with engine.begin() as c:
        buro = str(c.execute(text("INSERT INTO buro (ad) VALUES ('Parola Sınırı Bürosu') RETURNING id")).scalar_one())
        e_posta = f"sinir-{buro}@ornek.test"
        kimlik = yonetim.kullanici_ekle(c, buro_id=buro, ad_soyad="Av. Sınır", e_posta=e_posta, rol="avukat",
                                        parola=PAROLA)
    try:
        istemci = TestClient(app)
        assert _giris(istemci, e_posta).status_code == 200
        ikinci = TestClient(app)                      # aynı hesabın başka bir cihazdaki oturumu
        assert _giris(ikinci, e_posta).status_code == 200
        govde = {"mevcut": "Tahmin-Parola-0000", "yeni": "Yeni-Sentetik-Parola-1"}
        for _ in range(ayarlar.GIRIS_KILIT_ESIGI - 1):
            assert istemci.post("/oturum/parola", json=govde).status_code == 422
        with engine.connect() as c:
            assert _kullanici(c, kimlik).basarisiz_giris == ayarlar.GIRIS_KILIT_ESIGI - 1
        son = istemci.post("/oturum/parola", json=govde)
        assert son.status_code == 401 and "kilitlendi" in son.json()["detail"]
        # Tüm oturumlar kapandı; doğru parolayla bile giriş kilit süresince açılmaz
        assert istemci.get("/oturum/ben").status_code == 401
        assert ikinci.get("/oturum/ben").status_code == 401
        assert _giris(TestClient(app), e_posta).status_code == 401
        with engine.connect() as c:
            assert _kullanici(c, kimlik).kilitli
            nedenler = [a["neden"] for a in _denetim(c, "giris_basarisiz", kimlik)]
            assert nedenler.count("parola_degisiminde_yanlis_parola") == ayarlar.GIRIS_KILIT_ESIGI
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM oturum WHERE kullanici_id = :k"), {"k": kimlik})
            for tablo in ("denetim_kaydi", "kullanici"):
                c.execute(text(f"DELETE FROM {tablo} WHERE buro_id = :b"), {"b": buro})
            c.execute(text("DELETE FROM buro WHERE id = :b"), {"b": buro})
