"""Reddedilen erişim denemelerinin denetim kaydına yazılması. Tüm veriler sentetiktir."""

import uuid
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.belge.api import ayri_islem, depolama_al
from app.belge.metin_cikarma import gorevi_isle
from app.belge.yukleme import belge_yukle
from app.kimlik.api import gecerli_kullanici
from app.main import app
from conftest import basliktan_kullanici, ekle
from test_belge import pdf_uret


def _yetkisiz_avukat(conn, buro):
    return ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yetkisiz', :e, 'avukat')",
        b=buro, e=f"yetkisiz-{uuid.uuid4().hex[:8]}@ornek.test",
    )


def _yabanci(conn):
    buro = ekle(conn, "INSERT INTO buro (ad) VALUES ('Başka Büro')")
    kullanici = ekle(
        conn,
        "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
        "VALUES (:b, 'Av. Yabancı', 'yabanci@ornek.test', 'yonetici')",
        b=buro,
    )
    return buro, kullanici


def _redler(conn, kullanici_id):
    return conn.execute(
        text(
            "SELECT buro_id, hedef_tur, hedef_id, ayrinti FROM denetim_kaydi "
            "WHERE eylem = 'erisim_reddi' AND kullanici_id = :k ORDER BY zaman, id"
        ),
        {"k": kullanici_id},
    ).all()


def _al(istemci, yol, kullanici):
    return istemci.get(yol, headers={"X-Kullanici-Id": str(kullanici)})


def _belge(conn, dava, depolama):
    return belge_yukle(conn, depolama, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                       orijinal_ad="gizli.pdf", veri=pdf_uret("Gizli sentetik belge"))["id"]


def test_yetkisiz_listeleme_denemesi_kaydedilir(conn, dava, istemci):
    yetkisiz = _yetkisiz_avukat(conn, dava["buro"])
    assert _al(istemci, f"/davalar/{dava['dava']}/belgeler", yetkisiz).status_code == 403
    (red,) = _redler(conn, yetkisiz)
    assert red.buro_id == dava["buro"]
    assert (red.hedef_tur, red.hedef_id) == ("belge_listesi", dava["dava"])
    assert red.ayrinti == {"neden": "yetki_yok", "istenen_eylem": "goruntuleme", "durum_kodu": 403}


def test_baska_buronun_belgesine_deneme_deneyenin_burosuna_kaydedilir(conn, dava, depolama, istemci):
    belge_id = _belge(conn, dava, depolama)
    yabanci_buro, yabanci = _yabanci(conn)
    assert _al(istemci, f"/belgeler/{belge_id}/dosya", yabanci).status_code == 404
    (red,) = _redler(conn, yabanci)
    assert red.buro_id == yabanci_buro
    assert (red.hedef_tur, red.hedef_id) == ("belge", belge_id)
    assert red.ayrinti == {"neden": "bulunamadi", "istenen_eylem": "disa_aktarim", "durum_kodu": 404}
    # Belgenin sahibi büronun kaydına deneyenin kimliği yazılmaz
    sahip_buro = conn.execute(
        text("SELECT count(*) FROM denetim_kaydi WHERE eylem = 'erisim_reddi' AND buro_id = :b"),
        {"b": dava["buro"]},
    ).scalar_one()
    assert sahip_buro == 0


def test_sayfa_denemesinde_sayfa_no_kaydedilir(conn, dava, depolama, istemci):
    belge_id = _belge(conn, dava, depolama)
    yetkisiz = _yetkisiz_avukat(conn, dava["buro"])
    assert _al(istemci, f"/belgeler/{belge_id}/sayfalar/3", yetkisiz).status_code == 403
    (red,) = _redler(conn, yetkisiz)
    assert red.ayrinti["sayfa_no"] == 3 and red.ayrinti["istenen_eylem"] == "goruntuleme"


def test_yetkisiz_yukleme_denemesi_kaydedilir_dosya_saklanmaz(conn, dava, depolama, istemci, tmp_path):
    yetkisiz = _yetkisiz_avukat(conn, dava["buro"])
    yanit = istemci.post(
        f"/davalar/{dava['dava']}/belgeler",
        files={"dosya": ("deneme.pdf", pdf_uret("x"), "application/pdf")},
        headers={"X-Kullanici-Id": str(yetkisiz)},
    )
    assert yanit.status_code == 403
    (red,) = _redler(conn, yetkisiz)
    assert (red.hedef_tur, red.hedef_id, red.ayrinti["istenen_eylem"]) == ("dava_dosyasi", dava["dava"], "yukleme")
    assert not any(tmp_path.rglob("*.*"))


def test_olmayan_belge_denemesi_kaydedilir(conn, dava, istemci):
    hayali = uuid.uuid4()
    assert _al(istemci, f"/belgeler/{hayali}", dava["kullanici"]).status_code == 404
    (red,) = _redler(conn, dava["kullanici"])
    assert (red.hedef_id, red.ayrinti["neden"]) == (hayali, "bulunamadi")


def test_tanimsiz_kullanici_kaydedilemez_ama_reddedilir(conn, dava, istemci):
    bilinmeyen = uuid.uuid4()
    assert _al(istemci, f"/davalar/{dava['dava']}/belgeler", bilinmeyen).status_code == 404
    assert _redler(conn, bilinmeyen) == []


def test_yetkili_kullanicinin_olmayan_sayfasi_erisim_reddi_degildir(conn, dava, depolama, istemci):
    belge_id = _belge(conn, dava, depolama)
    gorevi_isle(conn, depolama)
    assert _al(istemci, f"/belgeler/{belge_id}/sayfalar/9", dava["kullanici"]).status_code == 404
    assert _redler(conn, dava["kullanici"]) == []


def test_red_kaydi_yazilamasa_da_yanit_degismez(conn, dava, istemci):
    @contextmanager
    def bozuk_islem():
        raise RuntimeError("veritabanına ulaşılamadı")
        yield  # pragma: no cover

    app.dependency_overrides[ayri_islem] = lambda: bozuk_islem
    yetkisiz = _yetkisiz_avukat(conn, dava["buro"])
    assert _al(istemci, f"/davalar/{dava['dava']}/belgeler", yetkisiz).status_code == 403


# --- Gerçek işlemlerle: istek geri alınsa da red kaydı kalır ---------------

@pytest.fixture
def kalici_veri(engine):
    """Kalıcı (commit edilmiş) sentetik büro, dava ve yetkisiz avukat; test sonunda silinir."""
    with engine.begin() as c:
        buro = ekle(c, "INSERT INTO buro (ad) VALUES ('Kalıcı Test Bürosu')")
        avukat = ekle(c, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Av. Sahip', :e, 'avukat')", b=buro, e=f"sahip-{buro}@ornek.test")
        yetkisiz = ekle(c, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                           "VALUES (:b, 'Av. Yetkisiz', :e, 'avukat')", b=buro, e=f"yetkisiz-{buro}@ornek.test")
        muvekkil = ekle(c, "INSERT INTO muvekkil (buro_id, tur, ad_unvan) VALUES (:b, 'gercek_kisi', 'Sentetik')",
                        b=buro)
        dava = ekle(c, "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, olusturan_kullanici_id) "
                       "VALUES (:b, :m, 'K/1', 'Kalıcı', :k)", b=buro, m=muvekkil, k=avukat)
    yield {"buro": buro, "yetkisiz": yetkisiz, "dava": dava}
    with engine.begin() as c:
        for tablo in ("denetim_kaydi", "dava_dosyasi", "muvekkil", "kullanici"):
            c.execute(text(f"DELETE FROM {tablo} WHERE buro_id = :b"), {"b": buro})
        c.execute(text("DELETE FROM buro WHERE id = :b"), {"b": buro})


def test_red_kaydi_isteğin_geri_alinmasindan_etkilenmez(engine, kalici_veri, tmp_path):
    from app.belge.depolama import YerelDepolama

    # İstek bağlantısı ve ayrı işlem gerçek; depolama geçici klasöre yönlenir, kullanıcı başlıktan okunur
    app.dependency_overrides[depolama_al] = lambda: YerelDepolama(tmp_path)
    app.dependency_overrides[gecerli_kullanici] = basliktan_kullanici
    try:
        yanit = TestClient(app).get(
            f"/davalar/{kalici_veri['dava']}/belgeler",
            headers={"X-Kullanici-Id": str(kalici_veri["yetkisiz"])},
        )
    finally:
        app.dependency_overrides.clear()
    assert yanit.status_code == 403
    with engine.connect() as c:
        redler = _redler(c, kalici_veri["yetkisiz"])
    assert len(redler) == 1 and redler[0].ayrinti["neden"] == "yetki_yok"
