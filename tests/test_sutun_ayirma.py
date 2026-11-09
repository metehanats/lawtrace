"""OCR metin kurma ve sütun ayırma kuralları (Tesseract gerektirmez).

Kelime konumları elle verilir: 300 dpi'da ~40 piksel yüksekliğinde kelimeler.
Sol sütun x=200'de, sağ sütun x=1300'de başlar; sol satırlar ~1050-1240'ta biter,
yani sütun boşluğu gerçek belgelerdeki gibi kelime yüksekliğinin 1,5-7 katıdır.
"""

from app.belge.ocr import Kelime, _metni_kur

YUKSEKLIK = 40
SATIR_ARASI = 72
HARF = 36


def _satir(no: int, parcalar: list[tuple[int, str]]) -> list[Kelime]:
    """parcalar: (başlangıç x, metin) listesi; metin kelimelere bölünür."""
    kelimeler, ust = [], 400 + no * SATIR_ARASI
    for x, metin in parcalar:
        for kelime in metin.split():
            kelimeler.append(Kelime(kelime, 95.0, x, x + HARF * len(kelime), ust, ust + YUKSEKLIK))
            x += HARF * len(kelime) + 15
    return kelimeler


def _kenarlar():
    # x0/x1 hesaplanırken sayfa genişliği tam olsun diye tam genişlikli bir başlık satırı
    return _satir(-2, [(200, "BAŞLIK"), (2100, "SAYFA")])


SOL = [
    "Davacı, davalıya mal teslim",
    "etmiş ve bedeli ödenmemiştir.",
    "davalıya ihtarname gönderilmiş",
    "ancak sonuç alınamamıştır.",
]
SAG = [
    "Davalı, malların ayıplı olduğunu",
    "ve tutanakla tespit edildiğini",
    "ileri sürmekte ve takas yapıldığını",
    "beyan etmektedir.",
]


def test_iki_sutunlu_duzyazi_ayrilir():
    satirlar = [_satir(i, [(200, s), (1300, d)]) for i, (s, d) in enumerate(zip(SOL, SAG))]
    metin = _metni_kur([[_kenarlar()], satirlar])
    sol = metin.index("Davacı,")
    sag = metin.index("Davalı,")
    # Sol sütunun tamamı sağ sütundan önce gelir, satırlar birleşmez
    assert sol < metin.index("ancak sonuç") < sag
    assert "teslim Davalı" not in metin


def test_tablo_satirlari_bolunmez():
    # Geometri iki sütunlu metinle aynı (hücreler sütun boşluğuna kadar dolu); tek fark,
    # hücrelerin büyük harfle başlaması: her satır yeni bir kalem
    tablo = [
        ("Satış sözleşmesi ve ekleri", "Taraflarca imzalanmış sözleşme"),
        ("Teslim tutanağı ve irsaliye", "Malların teslim edildiğini gösterir"),
        ("Banka hesap dökümleri seti", "Ödemenin yapılmadığını gösterir"),
        ("Tanık Hüseyin Aksoy beyanı", "Teslimat sırasında depodaydı"),
    ]
    satirlar = [_satir(i, [(200, s), (1300, d)]) for i, (s, d) in enumerate(tablo)]
    metin = _metni_kur([[_kenarlar()], satirlar])
    assert "Banka hesap dökümleri seti Ödemenin yapılmadığını gösterir" in metin


def test_dikey_cizgi_varsa_bolunmez():
    satirlar = [_satir(i, [(200, s), (1300, d)]) for i, (s, d) in enumerate(zip(SOL, SAG))]
    # Düzyazı gibi görünse de sütun boşluğunda tablo çizgisi var
    metin = _metni_kur([[_kenarlar()], satirlar], dikey_cizgi_var=lambda x0, x1, y0, y1: True)
    assert "Davacı, davalıya mal teslim Davalı, malların ayıplı olduğunu" in metin


def test_iki_satirlik_yan_yana_metin_bolunmez():
    satirlar = [_satir(i, [(200, s), (1300, d)]) for i, (s, d) in enumerate(zip(SOL[:2], SAG[:2]))]
    metin = _metni_kur([[_kenarlar()], satirlar])
    assert "Davacı, davalıya mal teslim Davalı," in metin


def test_tek_sutunlu_metin_aynen_kalir():
    satirlar = [
        _satir(0, [(200, "Ödenmeyen fatura bedeli 386.420,50 TL olup yıllık faiz oranı yüksektir.")]),
        _satir(1, [(200, "davalı şirket borcun bir kısmını kabul etmiştir ve bu durum tutanakla sabittir.")]),
        _satir(2, [(200, "mahkemece bilirkişi incelemesi yapılmasına karar verilmiştir.")]),
    ]
    metin = _metni_kur([satirlar])
    assert metin.splitlines() == [
        "Ödenmeyen fatura bedeli 386.420,50 TL olup yıllık faiz oranı yüksektir.",
        "davalı şirket borcun bir kısmını kabul etmiştir ve bu durum tutanakla sabittir.",
        "mahkemece bilirkişi incelemesi yapılmasına karar verilmiştir.",
    ]


def test_paragraflar_bos_satirla_ayrilir():
    metin = _metni_kur([[_satir(0, [(200, "Birinci paragraf")])], [_satir(2, [(200, "İkinci paragraf")])]])
    assert metin == "Birinci paragraf\n\nİkinci paragraf"


# --- Üç ve daha fazla sütun --------------------------------------------------

UC = [
    ["Davacı, aracın kavşakta", "durduğunu ve davalının", "arkadan çarptığını beyan", "etmiştir."],
    ["Davalı, davacının ani", "fren yaptığını ve kusurun", "da paylaşılması gerektiğini", "ileri sürmüştür."],
    ["Tanık Elif Şahin, ışığın", "kırmızı yandığını ve", "davacının durmuş olduğunu", "görmüştür."],
]


def _uc_sutun(satirlar: list[list[str]], x=(200, 1250, 2300)) -> list[list]:
    # Harf genişliği 36 px: en uzun satır ~950 px, sütunlar arası boşluk ~100 px
    return [_satir(i, [(xx, sutun[i]) for xx, sutun in zip(x, satirlar) if i < len(sutun)])
            for i in range(max(len(s) for s in satirlar))]


def test_uc_sutunlu_duzyazi_soldan_saga_ayrilir():
    metin = _metni_kur([[_kenarlar()], _uc_sutun(UC)])
    satirlar = metin.splitlines()
    # Her sütun kendi içinde bütün, sırayla: önce davacı, sonra davalı, sonra tanık
    assert satirlar.index("Davacı, aracın kavşakta") < satirlar.index("etmiştir.") \
        < satirlar.index("Davalı, davacının ani") < satirlar.index("ileri sürmüştür.") \
        < satirlar.index("Tanık Elif Şahin, ışığın") < satirlar.index("görmüştür.")
    assert "kavşakta Davalı" not in metin


def test_uc_sutunda_kisa_son_satir_dogru_sutuna_gider():
    # Son satırda yalnızca birinci ve ikinci sütunda metin var
    sutunlar = [UC[0], UC[1], UC[2][:3]]
    satirlar = _metni_kur([[_kenarlar()], _uc_sutun(sutunlar)]).splitlines()
    assert satirlar.index("ileri sürmüştür.") < satirlar.index("Tanık Elif Şahin, ışığın")


def test_sutun_araligindaki_gurultu_isareti_atilir():
    satirlar = _uc_sutun(UC)
    # Tesseract sütun aralığını "—" olarak okumuş
    for s in satirlar[:3]:
        s.append(Kelime("—", 40.0, 1190, 1215, s[0].ust, s[0].alt))
        s.sort(key=lambda k: k.sol)
    metin = _metni_kur([[_kenarlar()], satirlar])
    assert "—" not in metin
    assert "Davacı, aracın kavşakta" in metin.splitlines()


def test_uc_sutunlu_tablo_bolunmez():
    tablo = [
        ("Satış sözleşmesi aslı", "Taraflarca imzalanmış belge", "Dosyada mevcut belge"),
        ("Teslim tutanağı ve irsaliye", "Malların teslimini gösterir", "Davalıdan istenecek"),
        ("Banka hesap dökümleri", "Ödemenin yapılmadığını gösterir", "Bankadan celbedilecek"),
        ("Tanık Hüseyin Aksoy", "Teslimatta depoda bulunmuştur", "Duruşmada dinlenecek"),
    ]
    satirlar = [_satir(i, [(200, a), (1450, b), (2700, c)]) for i, (a, b, c) in enumerate(tablo)]
    metin = _metni_kur([[_kenarlar()], satirlar])
    assert "Banka hesap dökümleri Ödemenin yapılmadığını gösterir Bankadan celbedilecek" in metin
