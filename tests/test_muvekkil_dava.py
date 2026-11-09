"""Müvekkil ve dava oluşturma, şifreleme ve dosya erişimi yönetimi testleri. Tüm veriler sentetiktir."""

import uuid

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app import kripto
from app.dava.hizmet import tckn_gecerli
from conftest import ekle


def sentetik_tckn(ilk_dokuz: str = "123456789") -> str:
    """Sağlama haneleri doğru, uydurma bir T.C. kimlik numarası üretir."""
    h = [int(c) for c in ilk_dokuz]
    onuncu = ((h[0] + h[2] + h[4] + h[6] + h[8]) * 7 - (h[1] + h[3] + h[5] + h[7])) % 10
    onbirinci = (sum(h) + onuncu) % 10
    return f"{ilk_dokuz}{onuncu}{onbirinci}"


def _istek(istemci, yontem, yol, kullanici, **kw):
    return istemci.request(yontem, yol, headers={"X-Kullanici-Id": str(kullanici)}, **kw)


def _kullanici(conn, dava, rol, ad):
    return ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) VALUES (:b, :a, :e, :r)",
                b=dava["buro"], a=ad, e=f"{uuid.uuid4().hex[:8]}@ornek.test", r=rol)


def _denetim(conn, eylem, hedef_tur, hedef_id=None):
    return conn.execute(
        text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = :e AND hedef_tur = :t "
             "AND (CAST(:h AS UUID) IS NULL OR hedef_id = CAST(:h AS UUID)) ORDER BY id"),
        {"e": eylem, "t": hedef_tur, "h": hedef_id},
    ).scalars().all()


def _muvekkil_olustur(istemci, kullanici, **alanlar):
    govde = {"tur": "gercek_kisi", "ad_unvan": "Sentetik Kişi", **alanlar}
    return _istek(istemci, "POST", "/muvekkiller", kullanici, json=govde)


# --- Şifreleme ---------------------------------------------------------

def test_sifreleme_gidis_donus_ve_kayda_baglilik():
    kayit = uuid.uuid4()
    sifreli = kripto.sifrele("12345678901", kayit_id=kayit, alan="kimlik_no")
    assert b"12345678901" not in sifreli and sifreli[:2] == b"v1"
    assert kripto.coz(sifreli, kayit_id=kayit, alan="kimlik_no") == "12345678901"
    # Aynı değer her seferinde farklı şifrelenir
    assert kripto.sifrele("12345678901", kayit_id=kayit, alan="kimlik_no") != sifreli
    # Başka kayda ya da alana taşınan değer çözülemez
    with pytest.raises(InvalidTag):
        kripto.coz(sifreli, kayit_id=uuid.uuid4(), alan="kimlik_no")
    with pytest.raises(InvalidTag):
        kripto.coz(sifreli, kayit_id=kayit, alan="iletisim")


def test_arama_ozeti_sabit_ve_anahtarli(monkeypatch):
    birinci = kripto.arama_ozeti("12345678901", alan="kimlik_no")
    assert birinci == kripto.arama_ozeti("12345678901", alan="kimlik_no")
    monkeypatch.setenv("MUVEKKIL_ANAHTARI", kripto.anahtar_uret())
    assert kripto.arama_ozeti("12345678901", alan="kimlik_no") != birinci


def test_anahtar_yoksa_acik_hata(monkeypatch):
    monkeypatch.delenv("MUVEKKIL_ANAHTARI")
    with pytest.raises(kripto.AnahtarYok):
        kripto.sifrele("x", kayit_id=uuid.uuid4(), alan="kimlik_no")


def test_tckn_dogrulama():
    assert tckn_gecerli(sentetik_tckn())
    assert not tckn_gecerli("12345678901")       # sağlama haneleri yanlış
    assert not tckn_gecerli("0" + sentetik_tckn()[1:])
    assert not tckn_gecerli("1234567890")


# --- Müvekkil ----------------------------------------------------------

def test_muvekkil_olusturulur_bilgiler_sifreli_saklanir(conn, dava, istemci):
    tckn = sentetik_tckn()
    yanit = _muvekkil_olustur(istemci, dava["kullanici"], ad_unvan="Ayşe Sentetik", kimlik_no=tckn,
                              telefon="0555 000 00 00", adres="Sentetik Mah. No: 1")
    assert yanit.status_code == 201, yanit.text
    muvekkil_id = yanit.json()["id"]

    satir = conn.execute(text("SELECT kimlik_no_sifreli, iletisim_sifreli, kimlik_no_ozet FROM muvekkil "
                              "WHERE id = :m"), {"m": muvekkil_id}).one()
    ham = bytes(satir.kimlik_no_sifreli) + bytes(satir.iletisim_sifreli)
    for duz in (tckn, "0555", "Sentetik Mah"):
        assert duz.encode() not in ham
    assert tckn not in satir.kimlik_no_ozet

    liste = _istek(istemci, "GET", "/muvekkiller", dava["kullanici"]).json()["muvekkiller"]
    kayit = next(m for m in liste if m["id"] == muvekkil_id)
    assert kayit["kimlik_no_maskeli"] == "•" * 9 + tckn[-2:]

    ayrinti = _istek(istemci, "GET", f"/muvekkiller/{muvekkil_id}", dava["kullanici"]).json()
    assert ayrinti["kimlik_no"] == tckn
    assert ayrinti["iletisim"] == {"telefon": "0555 000 00 00", "adres": "Sentetik Mah. No: 1"}
    assert len(_denetim(conn, "olusturma", "muvekkil", muvekkil_id)) == 1
    assert len(_denetim(conn, "goruntuleme", "muvekkil", muvekkil_id)) == 1


def test_ayni_kimlik_numarasi_ikinci_kez_eklenemez(dava, istemci):
    tckn = sentetik_tckn("234567891")
    assert _muvekkil_olustur(istemci, dava["kullanici"], kimlik_no=tckn).status_code == 201
    yanit = _muvekkil_olustur(istemci, dava["kullanici"], ad_unvan="Başka Ad", kimlik_no=tckn)
    assert yanit.status_code == 409 and "Sentetik Kişi" in yanit.json()["detail"]


def test_gecersiz_kimlik_numarasi_reddedilir(dava, istemci):
    assert _muvekkil_olustur(istemci, dava["kullanici"], kimlik_no="12345678901").status_code == 422
    assert _muvekkil_olustur(istemci, dava["kullanici"], tur="tuzel_kisi", kimlik_no="123").status_code == 422
    assert _muvekkil_olustur(istemci, dava["kullanici"], tur="tuzel_kisi", kimlik_no="1234567890").status_code == 201


def test_stajyer_muvekkil_olusturamaz_ve_deneme_kaydedilir(conn, dava, istemci):
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    assert _muvekkil_olustur(istemci, stajyer).status_code == 403
    (red,) = conn.execute(text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = 'erisim_reddi' "
                               "AND kullanici_id = :k"), {"k": stajyer}).scalars().all()
    assert red["istenen_eylem"] == "olusturma" and red["neden"] == "yetki_yok"


def test_stajyer_yalnizca_dosyalarinin_muvekkillerini_gorur(conn, dava, istemci):
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    _muvekkil_olustur(istemci, dava["kullanici"], ad_unvan="Görünmeyecek Müvekkil")
    assert _istek(istemci, "GET", "/muvekkiller", stajyer).json()["muvekkiller"] == []
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": dava["dava"], "k": stajyer})
    adlar = [m["ad_unvan"] for m in _istek(istemci, "GET", "/muvekkiller", stajyer).json()["muvekkiller"]]
    assert adlar == ["Sentetik Müvekkil"]


def test_baska_buronun_muvekkili_gorunmez(conn, dava, istemci):
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"]).json()["id"]
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yabancı', 'yabanci@ornek.test', 'yonetici')", b=diger)
    assert _istek(istemci, "GET", f"/muvekkiller/{muvekkil_id}", yabanci).status_code == 404
    assert all(m["id"] != muvekkil_id
               for m in _istek(istemci, "GET", "/muvekkiller", yabanci).json()["muvekkiller"])


# --- Müvekkil düzenleme -------------------------------------------------

def _muvekkil_guncelle(istemci, kullanici, muvekkil_id, **alanlar):
    govde = {"tur": "gercek_kisi", "ad_unvan": "Sentetik Kişi", **alanlar}
    return _istek(istemci, "PUT", f"/muvekkiller/{muvekkil_id}", kullanici, json=govde)


def test_muvekkil_duzenlenir_denetime_yalnizca_alan_adlari_yazilir(conn, dava, istemci):
    tckn, yeni_tckn = sentetik_tckn("345678912"), sentetik_tckn("456789123")
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"], kimlik_no=tckn, telefon="0555 111 11 11",
                                    adres="Eski Mah.").json()["id"]
    yanit = _muvekkil_guncelle(istemci, dava["kullanici"], muvekkil_id, ad_unvan="Yeni Sentetik Ad",
                               kimlik_no=yeni_tckn, telefon="0555 111 11 11", e_posta="yeni@ornek.test")
    assert yanit.status_code == 204, yanit.text
    ayrinti = _istek(istemci, "GET", f"/muvekkiller/{muvekkil_id}", dava["kullanici"]).json()
    assert ayrinti["ad_unvan"] == "Yeni Sentetik Ad" and ayrinti["kimlik_no"] == yeni_tckn
    # Boş gönderilen adres silinir
    assert ayrinti["iletisim"] == {"telefon": "0555 111 11 11", "e_posta": "yeni@ornek.test"}
    (kayit,) = _denetim(conn, "guncelleme", "muvekkil", muvekkil_id)
    assert kayit == {"alanlar": ["ad_unvan", "kimlik_no", "e_posta", "adres"]}
    assert yeni_tckn not in str(kayit)
    # Eski kimlik numarası serbest kalır
    assert _muvekkil_olustur(istemci, dava["kullanici"], kimlik_no=tckn).status_code == 201


def test_degisiklik_yoksa_denetime_yazilmaz(conn, dava, istemci):
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"], telefon="0555").json()["id"]
    assert _muvekkil_guncelle(istemci, dava["kullanici"], muvekkil_id, telefon=" 0555 ").status_code == 204
    assert _denetim(conn, "guncelleme", "muvekkil", muvekkil_id) == []


def test_duzenlemede_baskasinin_kimlik_numarasi_kullanilamaz(dava, istemci):
    tckn = sentetik_tckn("567891234")
    _muvekkil_olustur(istemci, dava["kullanici"], ad_unvan="İlk Sahip", kimlik_no=tckn)
    ikinci = _muvekkil_olustur(istemci, dava["kullanici"], ad_unvan="İkinci").json()["id"]
    yanit = _muvekkil_guncelle(istemci, dava["kullanici"], ikinci, kimlik_no=tckn)
    assert yanit.status_code == 409 and "İlk Sahip" in yanit.json()["detail"]
    # Kendi numarasını korumak mükerrer sayılmaz
    kendi = _muvekkil_olustur(istemci, dava["kullanici"], kimlik_no=sentetik_tckn("678912345")).json()["id"]
    assert _muvekkil_guncelle(istemci, dava["kullanici"], kendi, ad_unvan="Ad Değişti",
                              kimlik_no=sentetik_tckn("678912345")).status_code == 204


def test_stajyer_ve_baska_buro_muvekkili_duzenleyemez(conn, dava, istemci):
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"]).json()["id"]
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    assert _muvekkil_guncelle(istemci, stajyer, muvekkil_id, ad_unvan="Olmaz").status_code == 403
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yabancı', 'yabanci2@ornek.test', 'yonetici')", b=diger)
    assert _muvekkil_guncelle(istemci, yabanci, muvekkil_id, ad_unvan="Olmaz").status_code == 404
    assert conn.execute(text("SELECT ad_unvan FROM muvekkil WHERE id = :m"),
                        {"m": muvekkil_id}).scalar_one() == "Sentetik Kişi"


# --- Dava oluşturma ----------------------------------------------------

def _dava_olustur(istemci, kullanici, muvekkil_id, dosya_no="2026/77"):
    return _istek(istemci, "POST", "/davalar", kullanici,
                  json={"muvekkil_id": str(muvekkil_id), "dosya_no": dosya_no, "baslik": "Yeni Sentetik Dava"})


def test_dava_olusturulur_olusturan_sorumlu_olur(conn, dava, istemci):
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"]).json()["id"]
    yanit = _dava_olustur(istemci, dava["kullanici"], muvekkil_id)
    assert yanit.status_code == 201, yanit.text
    dava_id = yanit.json()["id"]
    erisim = _istek(istemci, "GET", f"/davalar/{dava_id}/erisimler", dava["kullanici"]).json()
    assert erisim["yonetebilir"] is True
    assert [(e["kullanici_id"], e["erisim_rolu"]) for e in erisim["erisimler"]] == [(str(dava["kullanici"]), "sorumlu")]
    assert len(_denetim(conn, "olusturma", "dava_dosyasi", dava_id)) == 1
    # Aynı dosya numarası ikinci kez açılamaz
    assert _dava_olustur(istemci, dava["kullanici"], muvekkil_id).status_code == 409


def test_baska_buronun_muvekkiline_dava_acilamaz(conn, dava, istemci):
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci_muvekkil = ekle(conn, "INSERT INTO muvekkil (buro_id, tur, ad_unvan) "
                                  "VALUES (:b, 'gercek_kisi', 'Yabancı Müvekkil')", b=diger)
    assert _dava_olustur(istemci, dava["kullanici"], yabanci_muvekkil).status_code == 422


def test_stajyer_dava_olusturamaz(conn, dava, istemci):
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    muvekkil_id = _muvekkil_olustur(istemci, dava["kullanici"]).json()["id"]
    assert _dava_olustur(istemci, stajyer, muvekkil_id).status_code == 403


# --- Dosya erişimi -----------------------------------------------------

def test_sorumlu_erisim_verir_ve_kaldirir(conn, dava, istemci):
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    yol = f"/davalar/{dava['dava']}/erisimler/{stajyer}"
    assert _istek(istemci, "PUT", yol, dava["kullanici"], json={"rol": "inceleyen"}).status_code == 204
    # Stajyer artık dosyayı görür
    assert _istek(istemci, "GET", f"/davalar/{dava['dava']}", stajyer).status_code == 200
    assert _denetim(conn, "erisim_degisikligi", "dava_dosyasi", dava["dava"]) == [
        {"kullanici_id": str(stajyer), "rol": "inceleyen"}]

    assert _istek(istemci, "DELETE", yol, dava["kullanici"]).status_code == 204
    assert _istek(istemci, "GET", f"/davalar/{dava['dava']}", stajyer).status_code == 403
    assert _denetim(conn, "erisim_degisikligi", "dava_dosyasi", dava["dava"])[-1] == {
        "kullanici_id": str(stajyer), "rol": None}


def test_inceleyen_erisim_yonetemez(conn, dava, istemci):
    inceleyen = _kullanici(conn, dava, "avukat", "Av. İnceleyen")
    diger = _kullanici(conn, dava, "avukat", "Av. Diğer")
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": dava["dava"], "k": inceleyen})
    assert _istek(istemci, "GET", f"/davalar/{dava['dava']}/erisimler", inceleyen).json()["yonetebilir"] is False
    yanit = _istek(istemci, "PUT", f"/davalar/{dava['dava']}/erisimler/{diger}", inceleyen, json={"rol": "inceleyen"})
    assert yanit.status_code == 403


def test_son_sorumlu_kaldirilamaz_ya_da_dusurulemez(conn, dava, istemci):
    yol = f"/davalar/{dava['dava']}/erisimler/{dava['kullanici']}"
    assert _istek(istemci, "DELETE", yol, dava["kullanici"]).status_code == 409
    assert _istek(istemci, "PUT", yol, dava["kullanici"], json={"rol": "inceleyen"}).status_code == 409
    # İkinci bir sorumlu eklenince ilk sorumlu ayrılabilir
    ikinci = _kullanici(conn, dava, "avukat", "Av. İkinci")
    _istek(istemci, "PUT", f"/davalar/{dava['dava']}/erisimler/{ikinci}", dava["kullanici"], json={"rol": "sorumlu"})
    assert _istek(istemci, "DELETE", yol, dava["kullanici"]).status_code == 204


def test_baska_buronun_kullanicisina_erisim_verilemez(conn, dava, istemci):
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yabancı', 'yabanci@ornek.test', 'avukat')", b=diger)
    yanit = _istek(istemci, "PUT", f"/davalar/{dava['dava']}/erisimler/{yabanci}", dava["kullanici"],
                   json={"rol": "inceleyen"})
    assert yanit.status_code == 422


def test_gecersiz_erisim_rolu(dava, istemci):
    yanit = _istek(istemci, "PUT", f"/davalar/{dava['dava']}/erisimler/{dava['kullanici']}", dava["kullanici"],
                   json={"rol": "sahip"})
    assert yanit.status_code == 422


def test_buro_kullanicilari_listesi_yalnizca_kendi_burosu(conn, dava, istemci):
    _kullanici(conn, dava, "stajyer", "Stj. Sentetik")
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
               "VALUES (:b, 'Yabancı', 'yabanci@ornek.test', 'avukat')", b=diger)
    adlar = {k["ad_soyad"] for k in _istek(istemci, "GET", "/kullanicilar", dava["kullanici"]).json()["kullanicilar"]}
    assert adlar == {"Av. Deneme Kişi", "Stj. Sentetik"}
