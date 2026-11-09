"""Avukatın etiket seçmesi: çelişki tespitini besler, otomatik etiketle ezilmez, yeniden analizde korunur.
Veriler sentetiktir."""

from sqlalchemy import text

from conftest import ekle
from test_celiski import _analiz, _celiskiler, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)


def _bulgular(istemci, dava):
    return _istek(istemci, "GET", f"/davalar/{dava['dava']}/bulgular", dava["kullanici"]).json()["bulgular"]


def _etiketle(istemci, dava, bulgu_id, etiket, kullanici=None):
    return _istek(istemci, "PUT", f"/bulgular/{bulgu_id}/etiket", kullanici or dava["kullanici"],
                  json={"etiket": etiket})


def test_secilen_etiket_celiski_dogurur_yazim_farki_onemsiz(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Eksper raporu.docx", "Eksper incelemesinde zarar 96.000,00 TL olarak hesaplanmıştır.")
    _yukle(conn, acik, depolama, "Cevap dilekçesi.docx", "Davalı şirket 69.000,00 TL ödemeyi yeterli görmektedir.")
    _analiz(conn, istemci, acik, depolama)
    assert _celiskiler(istemci, acik) == []          # sözlükte olmayan ifade: etiket yok, çelişki yok
    a, b = sorted((x for x in _bulgular(istemci, acik) if x["tur"] == "tutar"), key=lambda x: x["ozet"])

    assert _etiketle(istemci, acik, a["id"], "Hasar Bedeli").json()["etiket"] == "hasar bedeli"
    assert _etiketle(istemci, acik, b["id"], "  hasar   bedeli ").status_code == 200
    (c,) = _celiskiler(istemci, acik)
    assert c["tur"] == "tutar" and "hasar bedeli" in c["aciklama"]
    sonra = {x["id"]: x for x in _bulgular(istemci, acik)}
    assert sonra[a["id"]]["etiket_kaynak"] == "avukat"
    assert sonra[a["id"]]["dogrulama_durumu"] == "otomatik"          # etiket bir karar değildir
    ayrinti = conn.execute(text("SELECT ayrinti FROM denetim_kaydi WHERE eylem = 'guncelleme' AND hedef_id = :b"),
                           {"b": a["id"]}).scalar_one()
    assert ayrinti == {"islem": "etiket", "onceki": None, "yeni": "hasar bedeli"}

    # Yeniden analiz: incelenmemiş bulgular yeniden oluşturulur ama avukatın etiketi aynı konuma geri yazılır
    _analiz(conn, istemci, acik, depolama)
    yeni = [x for x in _bulgular(istemci, acik) if x["tur"] == "tutar"]
    assert {(x["etiket"], x["etiket_kaynak"]) for x in yeni} == {("hasar bedeli", "avukat")}
    assert len(_celiskiler(istemci, acik)) == 1


def test_etiketsiz_birakma_otomatik_etiketi_kaldirir_ve_kalici(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "A.docx", "Dava değeri: 1.000 TL")
    _yukle(conn, acik, depolama, "B.docx", "Dava değeri: 2.000 TL")
    _analiz(conn, istemci, acik, depolama)
    assert len(_celiskiler(istemci, acik)) == 1
    hedef = next(x for x in _bulgular(istemci, acik) if x["ozet"] == "2.000,00 TL")
    assert hedef["etiket"] == "dava değeri" and hedef["etiket_kaynak"] is None

    # Avukat: bu tutar dava değeri değil (ör. başka bir kalem) → etiketsiz
    assert _etiketle(istemci, acik, hedef["id"], None).status_code == 200
    assert _celiskiler(istemci, acik) == []
    # Başka bir işlem çelişkileri yeniden hesaplar; otomatik etiket geri gelmez
    diger = next(x for x in _bulgular(istemci, acik) if x["ozet"] == "1.000,00 TL")
    _istek(istemci, "POST", f"/bulgular/{diger['id']}/inceleme", acik["kullanici"], json={"karar": "onay"})
    tekrar = next(x for x in _bulgular(istemci, acik) if x["id"] == hedef["id"])
    assert (tekrar["etiket"], tekrar["etiket_kaynak"]) == (None, "avukat")
    assert _celiskiler(istemci, acik) == []


def test_kisi_bulgusu_uzun_etiket_ve_stajyer_reddedilir(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dilekçe.docx", "Dava değeri: 5.000 TL")
    _analiz(conn, istemci, acik, depolama)
    tutar = next(x for x in _bulgular(istemci, acik) if x["tur"] == "tutar")
    assert _etiketle(istemci, acik, tutar["id"], "x" * 41).status_code == 422
    stajyer = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Stj', 'stj-etiket@ornek.test', 'stajyer')", b=acik["buro"])
    conn.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'inceleyen')"),
                 {"d": acik["dava"], "k": stajyer})
    assert _etiketle(istemci, acik, tutar["id"], "dava değeri", stajyer).status_code == 403

    secenekler = _istek(istemci, "GET", "/etiketler", acik["kullanici"]).json()
    assert "dava değeri" in secenekler["tutar"] and "fesih tarihi" in secenekler["tarih"]
