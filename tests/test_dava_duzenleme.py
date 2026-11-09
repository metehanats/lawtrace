"""Dava dosyası düzenleme ve kapatma: kapalı dosya salt okunurdur. Veriler sentetiktir."""

from sqlalchemy import text

from app.belge.erisim import DOSYA_KAPALI
from conftest import ekle
from test_bulgu_etiket import _bulgular, _etiketle
from test_celiski import _analiz, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)
from test_belge import docx_uret


def _guncelle(istemci, dava, kullanici=None, **alanlar):
    mevcut = _istek(istemci, "GET", f"/davalar/{dava['dava']}", dava["kullanici"]).json()
    govde = {k: mevcut[k] for k in ("muvekkil_id", "dosya_no", "baslik", "dava_turu", "durum")}
    return _istek(istemci, "PUT", f"/davalar/{dava['dava']}", kullanici or dava["kullanici"], json={**govde, **alanlar})


def _kullanici(conn, dava, rol, ad):
    return ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) VALUES (:b, :a, :e, :r)",
                b=dava["buro"], a=ad, e=f"{rol}.{ad.split()[-1].lower()}@ornek.test", r=rol)


def _guncelleme_kayitlari(conn, dava):
    return conn.execute(text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = 'guncelleme' "
                             "AND hedef_tur = 'dava_dosyasi' AND hedef_id = :d ORDER BY id"),
                        {"d": dava["dava"]}).scalars().all()


def test_sorumlu_dosyayi_duzenler_denetime_eski_ve_yeni_yazilir(conn, dava, istemci):
    ayrinti = _istek(istemci, "GET", f"/davalar/{dava['dava']}", dava["kullanici"]).json()
    assert ayrinti["duzenleyebilir"] is True
    yeni_muvekkil = ekle(conn, "INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'tuzel_kisi', 'Yeni Ltd.')",
                         b=dava["buro"])
    yanit = _guncelle(istemci, dava, baslik="  Yeni Başlık ", dava_turu="Tazminat", muvekkil_id=str(yeni_muvekkil))
    assert yanit.status_code == 204, yanit.text
    sonra = _istek(istemci, "GET", f"/davalar/{dava['dava']}", dava["kullanici"]).json()
    assert (sonra["baslik"], sonra["dava_turu"], sonra["muvekkil"]) == ("Yeni Başlık", "Tazminat", "Yeni Ltd.")
    (kayit,) = _guncelleme_kayitlari(conn, dava)
    assert kayit["alanlar"]["baslik"] == ["Sentetik Dava", "Yeni Başlık"]
    assert kayit["alanlar"]["muvekkil_id"][1] == str(yeni_muvekkil)
    assert set(kayit["alanlar"]) == {"baslik", "dava_turu", "muvekkil_id"}
    # Değişiklik yoksa kayıt yazılmaz
    assert _guncelle(istemci, dava).status_code == 204
    assert len(_guncelleme_kayitlari(conn, dava)) == 1


def test_mukerrer_dosya_no_ve_baska_buro_muvekkili_reddedilir(conn, dava, istemci):
    ekle(conn, "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, olusturan_kullanici_id) "
               "SELECT buro_id, muvekkil_id, '2026/2', 'Diğer', olusturan_kullanici_id FROM dava_dosyasi WHERE id = :d",
         d=dava["dava"])
    assert _guncelle(istemci, dava, dosya_no="2026/2").status_code == 409
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(conn, "INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'gercek_kisi', 'Yabancı')", b=diger)
    assert _guncelle(istemci, dava, muvekkil_id=str(yabanci)).status_code == 422


def test_inceleyen_ve_stajyer_duzenleyemez_yonetici_duzenler(conn, dava, istemci):
    inceleyen = _kullanici(conn, dava, "avukat", "Av. İnceleyen")
    stajyer = _kullanici(conn, dava, "stajyer", "Stj. Sorumlu")
    for k, rol in ((inceleyen, "inceleyen"), (stajyer, "sorumlu")):
        conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, :r)"),
                     {"d": dava["dava"], "k": k, "r": rol})
        assert _istek(istemci, "GET", f"/davalar/{dava['dava']}", k).json()["duzenleyebilir"] is False
        assert _guncelle(istemci, dava, kullanici=k, baslik="Olmaz").status_code == 403
    yonetici = _kullanici(conn, dava, "yonetici", "Av. Yönetici")
    assert _guncelle(istemci, dava, kullanici=yonetici, durum="beklemede").status_code == 204


def test_kapali_dosya_salt_okunur_yeniden_acilabilir(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "A.docx", "Dava değeri: 1.000 TL")
    _analiz(conn, istemci, acik, depolama)
    (bulgu,) = [b for b in _bulgular(istemci, acik) if b["tur"] == "tutar"]

    assert _guncelle(istemci, acik, durum="kapali").status_code == 204
    # Okuma sürer
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}", acik["kullanici"]).json()["durum"] == "kapali"
    assert len(_bulgular(istemci, acik)) >= 1
    # Yazma işlemleri reddedilir
    yuklenen = _istek(istemci, "POST", f"/davalar/{acik['dava']}/belgeler", acik["kullanici"],
                      files={"dosya": ("B.docx", docx_uret("Yeni belge"), "application/octet-stream")})
    for yanit in (
        yuklenen,
        _istek(istemci, "POST", f"/davalar/{acik['dava']}/analiz", acik["kullanici"], json={}),
        _istek(istemci, "POST", f"/bulgular/{bulgu['id']}/inceleme", acik["kullanici"], json={"karar": "onay"}),
        _etiketle(istemci, acik, bulgu["id"], "dava değeri"),
        _guncelle(istemci, acik, baslik="Kapalıyken başlık"),
    ):
        assert yanit.status_code == 409, yanit.text
        assert yanit.json()["detail"] == DOSYA_KAPALI
    # Yeniden açılınca yazma yeniden mümkün
    assert _guncelle(istemci, acik, durum="acik").status_code == 204
    assert _istek(istemci, "POST", f"/bulgular/{bulgu['id']}/inceleme", acik["kullanici"],
                  json={"karar": "onay"}).status_code == 200
    durumlar = [k["alanlar"]["durum"] for k in _guncelleme_kayitlari(conn, acik)]
    assert durumlar == [["acik", "kapali"], ["kapali", "acik"]]
