"""İddia–delil haritası testleri: bölümleme, delil eşleme ve bağlar. Tüm veriler sentetiktir."""

import itertools

from sqlalchemy import text

from app.analiz.iddia import DegerBulgusu, DosyaBelgesi, Sayfa, bolumle, harita_olustur
from test_celiski import _analiz, _istek, _yukle, acik  # noqa: F401 (acik bir fikstürdür)

DEMO = [
    Sayfa(1, "T.C. İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ'NE\nDAVACI: Ayşe Yılmaz\nDAVALI: Çağlar Gıda A.Ş.\n"
             "KONU: 386.420,50 TL alacağın tahsili talebidir.\n"
             "AÇIKLAMALAR: Müvekkil, davalı şirketle 03.11.2024 tarihinde mal satış sözleşmesi imzalamış ve\n"
             "sözleşme konusu malları eksiksiz teslim etmiştir.\n"
             "Davalıya 17.02.2025 tarihinde ihtarname gönderilmiş, ancak ödeme yapılmamıştır."),
    Sayfa(2, "Davalı şirket, 12 Mart 2025 tarihli yazısıyla borcun bir kısmını kabul etmiştir.\n"
             "SONUÇ VE İSTEM: 386.420,50 TL alacağın faiziyle tahsiline karar verilmesini arz ederiz."),
]

NUMARALI = [
    Sayfa(1, "DAVA DİLEKÇESİ\nDAVACI: Ayşe Yılmaz\n\nAÇIKLAMALAR:\n"
             "1. Taraflar arasında 03.11.2024 tarihinde sözleşme imzalanmıştır.\n"
             "Sözleşmenin 4.2. maddesi cezai şart öngörür.\n"
             "2- Mallar teslim edilmiş, faturalar (Ek-3) davalıya gönderilmiştir.\n\n"
             "HUKUKİ SEBEPLER: TBK ve TTK.\n"
             "DELİLLER: 1- Mal satış sözleşmesi 2- Ek-3 fatura listesi; ihtarname, tanık Hüseyin Aksoy beyanı,\n"
             "İstanbul 3. İcra Müdürlüğü 2025/123 E. sayılı dosyası ve bilirkişi incelemesi.\n"
             "SONUÇ VE İSTEM: Davanın kabulüne karar verilmesini arz ederiz.\nSayfa 1/1"),
]


def _metinler(parcalar):
    return [p.metin for p in parcalar]


def test_basliktan_sonraki_paragraflar_iddiadir_sayfa_sonunda_kesilir():
    d = bolumle(DEMO)
    assert _metinler(d.iddialar) == [
        "Müvekkil, davalı şirketle 03.11.2024 tarihinde mal satış sözleşmesi imzalamış ve\n"
        "sözleşme konusu malları eksiksiz teslim etmiştir",
        "Davalıya 17.02.2025 tarihinde ihtarname gönderilmiş, ancak ödeme yapılmamıştır",
        "Davalı şirket, 12 Mart 2025 tarihli yazısıyla borcun bir kısmını kabul etmiştir",
    ]
    assert [p.sayfa_no for p in d.iddialar] == [1, 1, 2]
    # Konum sayfa metnindeki yeri gösterir (kaynakta işaretlenebilir)
    for p in d.iddialar:
        assert DEMO[p.sayfa_no - 1].metin[p.bas:p.bit] == p.metin
    assert d.deliller == []


def test_numarali_iddia_numaradan_numaraya_ve_delil_kalemleri():
    d = bolumle(NUMARALI)
    assert _metinler(d.iddialar) == [
        "Taraflar arasında 03.11.2024 tarihinde sözleşme imzalanmıştır.\nSözleşmenin 4.2. maddesi cezai şart öngörür",
        "Mallar teslim edilmiş, faturalar (Ek-3) davalıya gönderilmiştir",
    ]
    assert _metinler(d.deliller) == [
        "Mal satış sözleşmesi", "Ek-3 fatura listesi", "ihtarname", "tanık Hüseyin Aksoy beyanı",
        "İstanbul 3. İcra Müdürlüğü 2025/123 E. sayılı dosyası", "bilirkişi incelemesi",
    ]
    for p in d.iddialar + d.deliller:
        assert NUMARALI[0].metin[p.bas:p.bit] == p.metin


def test_basliksiz_belge_bolumlenmez():
    d = bolumle([Sayfa(1, "Davalı şirket ödeme yapmayı reddetmemiştir.\nAçıklamalar yukarıdadır.")])
    assert d.iddialar == [] and d.deliller == []


# --- Harita -----------------------------------------------------------------

_sayac = itertools.count()


def _belge(ad, *metinler):
    return DosyaBelgesi(f"b-{ad}", ad, [Sayfa(i, m) for i, m in enumerate(metinler, 1)])


def _deger(belge, metin, deger_metni, deger, tur="tarih", durum="otomatik", sayfa=1):
    bas = metin.index(deger_metni)
    return DegerBulgusu(next(_sayac), belge.id, sayfa, tur, deger, deger_metni, bas, bas + len(deger_metni),
                        metin, 0, len(metin), durum)


def test_delil_listesi_dosyadaki_belgelerle_eslesir_eksikler_isaretlenir():
    dilekce = _belge("Dava dilekçesi.pdf", NUMARALI[0].metin)
    belgeler = [dilekce, _belge("Mal satış sözleşmesi.pdf", "MAL SATIŞ SÖZLEŞMESİ\nSözleşme tarihi: 03.11.2024"),
                _belge("EK-3 Fatura listesi (tarama).pdf", "FATURA LİSTESİ")]
    (h,) = harita_olustur(belgeler, [])
    assert [(d.metin, d.tur, [b["belge_adi"] for b in d.belgeler]) for d in h.deliller] == [
        ("Mal satış sözleşmesi", "dosyada", ["Mal satış sözleşmesi.pdf"]),
        ("Ek-3 fatura listesi", "dosyada", ["EK-3 Fatura listesi (tarama).pdf"]),
        ("ihtarname", "eksik", []),
        ("tanık Hüseyin Aksoy beyanı", "belge_disi", []),
        ("İstanbul 3. İcra Müdürlüğü 2025/123 E. sayılı dosyası", "dis_kaynak", []),
        ("bilirkişi incelemesi", "belge_disi", []),
    ]


def test_iddia_baglari_ek_anilan_belge_ayni_deger_ve_celiski():
    dilekce = _belge("Dava dilekçesi.pdf", *[s.metin for s in DEMO])
    sozlesme_metni = "MAL SATIŞ SÖZLEŞMESİ\nSözleşme tarihi: 03.11.2024"
    sozlesme = _belge("Mal satış sözleşmesi.pdf", sozlesme_metni)
    ihtar = _belge("İhtarname - faks.pdf", "")
    cevap_metni = "CEVAP DİLEKÇESİ\nSözleşme tarihi 03.11.2024 değil 04.11.2024'tür."
    cevap = _belge("Cevap dilekçesi.docx", cevap_metni)
    iddia_tarihi = _deger(dilekce, DEMO[0].metin, "03.11.2024", "2024-11-03")
    karsi = _deger(cevap, cevap_metni, "04.11.2024", "2024-11-04")
    bulgular = [
        iddia_tarihi, karsi,
        _deger(sozlesme, sozlesme_metni, "03.11.2024", "2024-11-03"),
        _deger(cevap, cevap_metni, "03.11.2024", "2024-11-03"),     # dilekçe delil sayılmaz
    ]
    (h,) = harita_olustur([dilekce, sozlesme, ihtar, cevap], bulgular,
                          {iddia_tarihi.id: [("Sözleşme tarihi farklı.", karsi.id)]})
    assert h.belge_adi == "Dava dilekçesi.pdf"
    birinci, ikinci, ucuncu = h.iddialar
    assert sorted((b.tur, b.belge_adi) for b in birinci.baglar) == [
        ("anilan_belge", "Mal satış sözleşmesi.pdf"),
        ("ayni_deger", "Mal satış sözleşmesi.pdf"),
        ("celiski", "Cevap dilekçesi.docx"),
    ]
    ayni = next(b for b in birinci.baglar if b.tur == "ayni_deger")
    assert (ayni.sayfa_no, ayni.alinti) == (1, sozlesme_metni)
    assert [(b.tur, b.belge_adi) for b in ikinci.baglar] == [("anilan_belge", "İhtarname - faks.pdf")]
    assert ucuncu.baglar == [] and ucuncu.dayanaksiz and not birinci.dayanaksiz


def test_reddedilen_deger_bag_kurmaz_ek_atfi_baglanir():
    dilekce = _belge("Dava dilekçesi.docx", NUMARALI[0].metin)
    fatura_metni = "FATURA LİSTESİ\n03.11.2024 tarihli fatura"
    fatura = _belge("EK-3 Fatura listesi.pdf", fatura_metni)
    bulgular = [_deger(dilekce, NUMARALI[0].metin, "03.11.2024", "2024-11-03"),
                _deger(fatura, fatura_metni, "03.11.2024", "2024-11-03", durum="reddedildi")]
    birinci, ikinci = harita_olustur([dilekce, fatura], bulgular)[0].iddialar
    assert birinci.baglar == []
    assert [(b.tur, b.belge_adi) for b in ikinci.baglar] == [("ek_atfi", "EK-3 Fatura listesi.pdf")]


# --- Uygulama akışı (sahte model, gerçek veritabanı/işçi/API) ----------------

def test_harita_api_belgelerle_iliskilendirir_ozel_nitelikli_metni_okumaz(conn, acik, depolama, istemci):
    _yukle(conn, acik, depolama, "Dava dilekçesi.docx",
           "AÇIKLAMALAR:\n1. Taraflar arasında 03.11.2024 tarihinde mal satış sözleşmesi imzalanmıştır.\n"
           "2. Davacı alacağını tahsil edememiştir.\n"
           "DELİLLER: Mal satış sözleşmesi, ihtarname, tanık beyanı.\nSONUÇ VE İSTEM: Kabulüne karar verilmesi.")
    _yukle(conn, acik, depolama, "Mal satış sözleşmesi.docx", "MAL SATIŞ SÖZLEŞMESİ\nSözleşme tarihi: 03.11.2024")
    # Başlıkları olan ama özel nitelikli (onaysız) belge: metni okunmaz, dilekçe gibi haritalanmaz
    _yukle(conn, acik, depolama, "Rapor.docx", "AÇIKLAMALAR:\nHastane epikrizi ekte sunulmuştur, tanı: bel fıtığı.")
    _analiz(conn, istemci, acik, depolama)

    yanit = _istek(istemci, "GET", f"/davalar/{acik['dava']}/iddia-haritasi", acik["kullanici"])
    assert yanit.status_code == 200
    (h,) = yanit.json()["dilekceler"]
    assert h["belge_adi"] == "Dava dilekçesi.docx"
    birinci, ikinci = h["iddialar"]
    assert sorted((b["tur"], b["belge_adi"]) for b in birinci["baglar"]) == [
        ("anilan_belge", "Mal satış sözleşmesi.docx"), ("ayni_deger", "Mal satış sözleşmesi.docx")]
    assert not birinci["dayanaksiz"] and ikinci["dayanaksiz"]
    assert [(d["metin"], d["tur"]) for d in h["deliller"]] == [
        ("Mal satış sözleşmesi", "dosyada"), ("ihtarname", "eksik"), ("tanık beyanı", "belge_disi")]
    assert conn.execute(text("SELECT count(*) FROM denetim_kaydi WHERE eylem = 'goruntuleme' "
                             "AND hedef_tur = 'iddia_haritasi' AND hedef_id = :d"),
                        {"d": acik["dava"]}).scalar_one() == 1


def test_erisimi_olmayan_haritayi_goremez(conn, acik, istemci):
    from conftest import ekle
    yabanci = ekle(conn, "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol) "
                         "VALUES (:b, 'Yab', 'yab-iddia@ornek.test', 'avukat')", b=acik["buro"])
    assert _istek(istemci, "GET", f"/davalar/{acik['dava']}/iddia-haritasi", yabanci).status_code == 403
