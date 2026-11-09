"""Dava dosyası uçlarının testleri. Tüm veriler sentetiktir."""

from sqlalchemy import text

from conftest import ekle


def _al(istemci, yol, kullanici):
    return istemci.get(yol, headers={"X-Kullanici-Id": str(kullanici)})


def _ikinci_dava(conn, dava):
    muvekkil = ekle(conn, "INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'tuzel_kisi', 'Sentetik A.Ş.')",
                    b=dava["buro"])
    return ekle(
        conn,
        "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, olusturan_kullanici_id) "
        "VALUES (:b, :m, '2026/2', 'İkinci Dava', :k)",
        b=dava["buro"], m=muvekkil, k=dava["kullanici"],
    )


def test_avukat_yalnizca_erisimi_olan_davalari_gorur(conn, dava, istemci):
    _ikinci_dava(conn, dava)  # bu dosyaya erişim kaydı yok
    yanit = _al(istemci, "/davalar", dava["kullanici"])
    assert yanit.status_code == 200, yanit.text
    davalar = yanit.json()["davalar"]
    assert [d["dosya_no"] for d in davalar] == ["2026/1"]
    assert davalar[0]["muvekkil"] == "Sentetik Müvekkil" and davalar[0]["belge_sayisi"] == 0


def test_yonetici_burodaki_tum_davalari_gorur(conn, dava, istemci):
    _ikinci_dava(conn, dava)
    yonetici = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                          "VALUES (:b, 'Yönetici', 'yonetici@ornek.test', 'yonetici')", b=dava["buro"])
    davalar = _al(istemci, "/davalar", yonetici).json()["davalar"]
    assert sorted(d["dosya_no"] for d in davalar) == ["2026/1", "2026/2"]


def test_baska_buronun_davalari_listelenmez(conn, dava, istemci):
    diger = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yabancı', 'yabanci@ornek.test', 'yonetici')", b=diger)
    assert _al(istemci, "/davalar", yabanci).json()["davalar"] == []
    assert _al(istemci, f"/davalar/{dava['dava']}", yabanci).status_code == 404


def test_dava_ayrintisi_ve_denetim(conn, dava, istemci):
    yanit = _al(istemci, f"/davalar/{dava['dava']}", dava["kullanici"])
    assert yanit.status_code == 200 and yanit.json()["baslik"] == "Sentetik Dava"
    sayi = conn.execute(
        text("SELECT count(*) FROM denetim_kaydi WHERE eylem = 'goruntuleme' AND hedef_tur = 'dava_dosyasi' "
             "AND hedef_id = :d"), {"d": dava["dava"]},
    ).scalar_one()
    assert sayi == 1
