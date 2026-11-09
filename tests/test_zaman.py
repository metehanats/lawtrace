"""Zaman çizelgesi testleri: sıralama, birleştirme ve uygulama akışı. Tüm veriler sentetiktir."""

import itertools

from sqlalchemy import text

from app.analiz.zaman import TarihBulgusu, zaman_cizelgesi
from test_celiski import _analiz, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)

_sayac = itertools.count()


def _t(deger, belge="Dilekçe", etiket=None, durum="otomatik", sayfa=1):
    return TarihBulgusu(next(_sayac), deger, deger, etiket, belge, belge, sayfa, f"... {deger} ...", None, None,
                        durum)


def test_kronolojik_sira_ve_gun_farki():
    olaylar = zaman_cizelgesi([_t("2025-02-28"), _t("2024-11-03"), _t("2025-02-17")])
    assert [o.tarih for o in olaylar] == ["2024-11-03", "2025-02-17", "2025-02-28"]
    assert [o.onceki_olaydan_gun for o in olaylar] == [None, 106, 11]


def test_ayni_tarih_tek_olay_kaynaklar_birlesir_etiketler_toplanir():
    (o,) = zaman_cizelgesi([_t("2024-11-03", "Cevap", "sözleşme tarihi"), _t("2024-11-03", "Dilekçe"),
                            _t("2024-11-03", "Bilirkişi", "sözleşme tarihi", durum="onaylandi")])
    assert o.etiketler == ["sözleşme tarihi"] and o.onayli
    # Onaylı kaynak önce, sonra belge adına göre
    assert [k.belge_adi for k in o.kaynaklar] == ["Bilirkişi", "Cevap", "Dilekçe"]


def test_eksik_tarih_doneminin_basina_dizilir_gun_farkina_karismaz():
    olaylar = zaman_cizelgesi([_t("2025-03-15"), _t("2025-03"), _t("2025"), _t("2025-03-01")])
    assert [(o.tarih, o.hassasiyet) for o in olaylar] == [
        ("2025", "yil"), ("2025-03", "ay"), ("2025-03-01", "gun"), ("2025-03-15", "gun")]
    assert [o.onceki_olaydan_gun for o in olaylar] == [None, None, None, 14]


def test_reddedilen_bulgu_cizelgeye_girmez():
    olaylar = zaman_cizelgesi([_t("2024-11-03", durum="reddedildi"), _t("2024-11-05")])
    assert [o.tarih for o in olaylar] == ["2024-11-05"]
    assert zaman_cizelgesi([_t("2024-11-03", durum="reddedildi")]) == []


def test_celiskili_olay_isaretlenir():
    a, b = _t("2024-11-03", etiket="sözleşme tarihi"), _t("2024-11-04", "Cevap", "sözleşme tarihi")
    olaylar = zaman_cizelgesi([a, b, _t("2025-01-01")], {a.id: "farklı", b.id: "farklı"})
    assert [o.celiskili for o in olaylar] == [True, True, False]
    assert olaylar[0].celiski_aciklamalari == ["farklı"]


# --- Uygulama akışı (sahte model, gerçek veritabanı/işçi/API) ----------------

def _cizelge(istemci, dava, kullanici=None):
    return _istek(istemci, "GET", f"/davalar/{dava['dava']}/zaman-cizelgesi", kullanici or dava["kullanici"])


def test_cizelge_belgeler_arasi_olaylari_kaynaklariyla_dizer(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dava dilekçesi.docx",
           "Sözleşme tarihi 03.11.2024 olup teslim yapılmıştır.\n"
           "İş akdi 28 Şubat 2025 tarihinde feshedilmiştir.")
    _yukle(conn, acik, depolama, "Cevap dilekçesi.docx",
           "Sözleşme tarihi 04.11.2024'tür.\nİhtarname 17.02.2025 tarihinde tebliğ edilmiştir.\n"
           "Fesih 28.02.2025 tarihlidir.")
    _analiz(conn, istemci, acik, depolama)

    yanit = _cizelge(istemci, acik)
    assert yanit.status_code == 200
    olaylar = yanit.json()["olaylar"]
    assert [o["tarih"] for o in olaylar] == ["2024-11-03", "2024-11-04", "2025-02-17", "2025-02-28"]
    fesih = olaylar[-1]
    assert {k["belge_adi"] for k in fesih["kaynaklar"]} == {"Dava dilekçesi.docx", "Cevap dilekçesi.docx"}
    assert fesih["onceki_olaydan_gun"] == 11 and "fesih tarihi" in fesih["etiketler"]
    # Sözleşme tarihi çelişkisi her iki olayda işaretli; kaynak konumu bağlantı için gelir
    assert [o["celiskili"] for o in olaylar[:2]] == [True, True]
    assert all(k["bas"] is not None and k["sayfa_no"] == 1 for o in olaylar for k in o["kaynaklar"])

    # Çelişki "incelendi" yapılınca işaret kalkar
    (c,) = [c for c in _istek(istemci, "GET", f"/davalar/{acik['dava']}/celiskiler", acik["kullanici"]).json()[
        "celiskiler"] if c["tur"] == "tarih"]
    _istek(istemci, "PUT", f"/celiskiler/{c['id']}", acik["kullanici"], json={"durum": "incelendi"})
    assert not any(o["celiskili"] for o in _cizelge(istemci, acik).json()["olaylar"])

    # Görüntüleme denetime yazılır
    assert conn.execute(text("SELECT count(*) FROM denetim_kaydi WHERE eylem = 'goruntuleme' "
                             "AND hedef_tur = 'zaman_cizelgesi' AND hedef_id = :d"),
                        {"d": acik["dava"]}).scalar_one() == 1


def test_erisimi_olmayan_cizelgeyi_goremez(conn, acik, istemci):
    from conftest import ekle
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yab', 'yab-zaman@ornek.test', 'avukat')", b=acik["buro"])
    # Aynı bürodan ama dosyaya erişimi yok: 403 (başka büro olsaydı 404)
    assert _cizelge(istemci, acik, yabanci).status_code == 403
