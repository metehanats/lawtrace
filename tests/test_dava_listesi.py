"""Dava listesindeki "bekleyen iş" sayıları (Özet sekmesiyle aynı tanımlar). Veriler sentetiktir."""

from test_celiski import _analiz, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)


def _liste_satiri(istemci, dava):
    yanit = _istek(istemci, "GET", "/davalar", dava["kullanici"])
    assert yanit.status_code == 200
    return next(d for d in yanit.json()["davalar"] if d["id"] == str(dava["dava"]))


def test_bekleyen_is_sayilari_incelemeyle_azalir(conn, acik, depolama, istemci):
    bos = _liste_satiri(istemci, acik)
    assert (bos["incelenmemis_bulgu"], bos["acik_celiski"], bos["kontrol_ocr_sayfa"], bos["onay_bekleyen_belge"]) == (
        0, 0, 0, 0)

    _yukle(conn, acik, depolama, "Dava dilekçesi.docx", "Dava değeri: 386.420,50 TL")
    _yukle(conn, acik, depolama, "Bilirkişi raporu.docx", "Hesaplanan dava değeri 368.420,50 TL'dir.")
    # Özel nitelikli (sağlık) belge: avukat onayı bekler
    _yukle(conn, acik, depolama, "Rapor.docx", "Hastane epikrizi: tanı bel fıtığı.")
    _analiz(conn, istemci, acik, depolama)

    satir = _liste_satiri(istemci, acik)
    assert satir["incelenmemis_bulgu"] == 2 and satir["acik_celiski"] == 1 and satir["onay_bekleyen_belge"] == 1
    # Ayrıntı ucu da aynı alanları taşır
    ayrinti = _istek(istemci, "GET", f"/davalar/{acik['dava']}", acik["kullanici"]).json()
    assert (ayrinti["incelenmemis_bulgu"], ayrinti["acik_celiski"]) == (2, 1)

    # Hatalı bulgu reddedilince: incelenmemiş bir azalır, çelişki kalkar
    bulgular = _istek(istemci, "GET", f"/davalar/{acik['dava']}/bulgular", acik["kullanici"]).json()["bulgular"]
    yanlis = next(b for b in bulgular if b["ozet"] == "368.420,50 TL")
    _istek(istemci, "POST", f"/bulgular/{yanlis['id']}/inceleme", acik["kullanici"], json={"karar": "red"})
    sonra = _liste_satiri(istemci, acik)
    assert (sonra["incelenmemis_bulgu"], sonra["acik_celiski"]) == (1, 0)
