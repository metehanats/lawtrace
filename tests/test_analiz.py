"""Analiz çıkarımının modelden bağımsız testleri: normalleştirme, kaynak doğrulama, uydurma bulgunun reddi.

Gerçek model kullanılmaz; sahte model önceden belirlenmiş JSON döndürür.
"""

import pytest

from app.analiz.cikarim import (
    adlar_esit, alinti_bul, bulgulari_cikar, deger_alintida_mi, ham_bulguyu_dogrula, tarih_normalle, tutar_normalle,
)


class SahteModel:
    saglayici, model = "sahte", "sahte-1"

    def __init__(self, *yanitlar):
        self.yanitlar = list(yanitlar)
        self.istemler = []

    def json_tamamla(self, sistem, kullanici, sema):
        self.istemler.append(kullanici)
        return self.yanitlar.pop(0)


SAYFALAR = [
    "DAVACI: Ayşe Yılmaz\nKONU: 386.420,50 TL alacağın tahsili.\nSözleşme   03.11.2024 tarihinde imzalandı.",
    "Davalı Çağlar Gıda Sanayi ve Ticaret A.Ş. 12 Mart 2025 tarihli yazısıyla borcun 120.000 TL'lik kısmını kabul etti.",
]


@pytest.mark.parametrize("girdi, beklenen", [
    ("2024-11-03", "2024-11-03"), ("03.11.2024", "2024-11-03"), ("3/11/2024", "2024-11-03"),
    ("12 Mart 2025", "2025-03-12"), ("1 ŞUBAT 2019", "2019-02-01"), ("2020-03", "2020-03"), ("2021", "2021"),
    ("2024-13-01", None), ("31.02.2024x", None), ("dün", None),
])
def test_tarih_normalle(girdi, beklenen):
    assert tarih_normalle(girdi) == beklenen


@pytest.mark.parametrize("girdi, beklenen", [
    ("386420.50 TRY", "386420.50 TRY"), ("386.420,50 TL", "386420.50 TRY"), ("120.000 TL", "120000.00 TRY"),
    ("120.000 TRY", "120000.00 TRY"), ("₺5.000", "5000.00 TRY"), ("$2,000", "2000.00 USD"),
    ("2000 USD", "2000.00 USD"), ("1.250,75 EUR", "1250.75 EUR"), ("yüz bin lira", None), ("386420.50", None),
])
def test_tutar_normalle(girdi, beklenen):
    assert tutar_normalle(girdi) == beklenen


def test_adlar_esit_unvan_ve_harf_farki():
    assert adlar_esit("Av. Ece Kara", "Ece Kara")
    assert adlar_esit("İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ", "İstanbul 7. Asliye Ticaret Mahkemesi")
    assert not adlar_esit("Kemal Çağlar", "Çağlar Gıda Sanayi ve Ticaret A.Ş.")


def test_alinti_bosluk_ve_tirnak_farkina_dayanikli():
    bas, bit = alinti_bul(SAYFALAR[0], "Sözleşme 03.11.2024 tarihinde")
    assert SAYFALAR[0][bas:bit] == "Sözleşme   03.11.2024 tarihinde"
    assert alinti_bul("borcun 120.000 TL’lik kısmı", "120.000 TL'lik kısmı") is not None
    assert alinti_bul(SAYFALAR[0], "Sözleşme 04.11.2024 tarihinde") is None


def test_deger_alintida_mi():
    assert deger_alintida_mi("tutar", "386420.50 TRY", "KONU: 386.420,50 TL alacağın")
    assert not deger_alintida_mi("tutar", "999999.00 TRY", "KONU: 386.420,50 TL alacağın")
    assert deger_alintida_mi("tarih", "2025-03-12", "12 Mart 2025 tarihli yazısıyla")
    assert not deger_alintida_mi("kisi", "Mehmet Öz", "DAVACI: Ayşe Yılmaz")


@pytest.mark.parametrize("ham, neden", [
    ({"tur": "tutar", "deger": "500000.00 TRY", "alinti": "500.000 TL tazminat ödenecektir", "sayfa": 1},
     "alıntı belgede yok"),                                         # uydurma alıntı
    ({"tur": "tutar", "deger": "500000.00 TRY", "alinti": "386.420,50 TL alacağın tahsili", "sayfa": 1},
     "değer alıntıyla uyuşmuyor"),                                  # doğru alıntı, uydurma değer
    ({"tur": "tarih", "deger": "2024-01-03", "alinti": "Sözleşme 03.11.2024 tarihinde", "sayfa": 1},
     "değer alıntıyla uyuşmuyor"),                                  # yıl doğru, ay yanlış
    ({"tur": "tutar", "deger": "386420.00 TRY", "alinti": "386.420,50 TL alacağın tahsili", "sayfa": 1},
     "değer alıntıyla uyuşmuyor"),                                  # kuruşu yanlış
    ({"tur": "tarih", "deger": "geçen yıl", "alinti": "Sözleşme 03.11.2024 tarihinde", "sayfa": 1},
     "değer biçimi geçersiz"),
    ({"tur": "tarih", "deger": "2024-11-03", "alinti": "Sözleşme 03.11.2024 tarihinde", "sayfa": 7},
     "geçersiz sayfa"),
    ({"tur": "iddia", "deger": "x", "alinti": "x", "sayfa": 1}, "bilinmeyen tür"),
])
def test_dogrulanamayan_bulgu_reddedilir(ham, neden):
    assert ham_bulguyu_dogrula(ham, SAYFALAR) == neden


def test_ilk_olcumdeki_ay_hatasi_reddedilir():
    # qwen3.5:4b "1 Şubat 2019"u 2019-01-01 diye döndürmüştü; yalnızca yıla bakan denetimden geçiyordu
    sayfalar = ["Müvekkilim 1 Şubat 2019 tarihinden itibaren çalışmıştır."]
    ham = {"tur": "tarih", "deger": "2019-01-01", "alinti": "1 Şubat 2019 tarihinden", "sayfa": 1}
    assert ham_bulguyu_dogrula(ham, sayfalar) == "değer alıntıyla uyuşmuyor"
    ham["deger"] = "2019-02-01"
    assert ham_bulguyu_dogrula(ham, sayfalar).deger == "2019-02-01"


@pytest.mark.parametrize("alinti, beklenen", [
    ("03.11.2024 tarihli fatura", {"2024-11-03", "2024"}),
    ("2020 yılının Mart ayında başladık", {"2020-03", "2020"}),
    ("Mart 2020'de", {"2020-03", "2020"}),
    ("12 Mart 2025 tarihli yazısıyla", {"2025-03-12", "2025"}),
])
def test_alintidaki_tarihler(alinti, beklenen):
    from app.analiz.cikarim import alintidaki_tarihler
    assert alintidaki_tarihler(alinti) == beklenen


def test_sirket_eki_olan_kisi_kurum_sayilir_parantez_atilir():
    sayfalar = ["Davalı Ege Kırtasiye ve Yayıncılık Ltd. Şti. kiracıdır. Bilirkişi: Dr. Selma Koç (Mali Müşavir)"]
    sirket = ham_bulguyu_dogrula({"tur": "kisi", "deger": "Ege Kırtasiye ve Yayıncılık Ltd. Şti.",
                                  "alinti": "Davalı Ege Kırtasiye ve Yayıncılık Ltd. Şti.", "sayfa": 1}, sayfalar)
    assert sirket.tur == "kurum"
    kisi = ham_bulguyu_dogrula({"tur": "kisi", "deger": "Dr. Selma Koç (Mali Müşavir)",
                                "alinti": "Bilirkişi: Dr. Selma Koç (Mali Müşavir)", "sayfa": 1}, sayfalar)
    assert (kisi.tur, kisi.deger) == ("kisi", "Selma Koç")


def test_yanlis_sayfa_numarasi_dogru_sayfaya_baglanir():
    ham = {"tur": "kurum", "deger": "Çağlar Gıda Sanayi ve Ticaret A.Ş.",
           "alinti": "Davalı Çağlar Gıda Sanayi ve Ticaret A.Ş.", "sayfa": 1}
    bulgu = ham_bulguyu_dogrula(ham, SAYFALAR)
    assert bulgu.sayfa_no == 2 and SAYFALAR[1][bulgu.baslangic:bulgu.bitis] == bulgu.alinti


def test_bulgulari_cikar_dogrular_tekrarlari_atar():
    model = SahteModel({"bulgular": [
        {"tur": "kisi", "deger": "Ayşe Yılmaz", "alinti": "DAVACI: Ayşe Yılmaz", "sayfa": 1},
        {"tur": "kisi", "deger": "Ayşe YILMAZ", "alinti": "DAVACI: Ayşe Yılmaz", "sayfa": 1},     # tekrar
        {"tur": "tutar", "deger": "386.420,50 TL", "alinti": "386.420,50 TL alacağın tahsili", "sayfa": 1},
        {"tur": "tutar", "deger": "120000.00 TRY", "alinti": "borcun 120.000 TL'lik kısmını", "sayfa": 2},
        {"tur": "tarih", "deger": "2025-03-12", "alinti": "12 Mart 2025 tarihli yazısıyla", "sayfa": 2},
        {"tur": "kisi", "deger": "Hayali Kişi", "alinti": "tanık Hayali Kişi", "sayfa": 2},          # uydurma
    ]})
    sonuc = bulgulari_cikar(model, SAYFALAR, karma=False)
    assert [(b.tur, b.deger, b.sayfa_no) for b in sonuc.bulgular] == [
        ("kisi", "Ayşe Yılmaz", 1), ("tutar", "386420.50 TRY", 1),
        ("tutar", "120000.00 TRY", 2), ("tarih", "2025-03-12", 2),
    ]
    assert [neden for _, neden in sonuc.reddedilen] == ["alıntı belgede yok"]
    # İstem sayfa işaretlerini içerir
    assert "[SAYFA 1]" in model.istemler[0] and "[SAYFA 2]" in model.istemler[0]


def test_karma_kipte_tarih_tutar_kurallardan_ad_modelden_gelir():
    model = SahteModel({"bulgular": [
        {"tur": "kisi", "deger": "Ayşe Yılmaz", "alinti": "DAVACI: Ayşe Yılmaz", "sayfa": 1},
        # Karma kipte modelden gelen tarih yok sayılır (yanlış bile olsa)
        {"tur": "tarih", "deger": "1999-01-01", "alinti": "Sözleşme 03.11.2024 tarihinde", "sayfa": 1},
    ]})
    sonuc = bulgulari_cikar(model, SAYFALAR)
    assert sorted((b.tur, b.deger, b.sayfa_no) for b in sonuc.bulgular) == [
        ("kisi", "Ayşe Yılmaz", 1),
        ("tarih", "2024-11-03", 1), ("tarih", "2025-03-12", 2),
        ("tutar", "120000.00 TRY", 2), ("tutar", "386420.50 TRY", 1),
    ]
    assert sonuc.reddedilen == []
    # Modelden yalnızca kişi ve kurum istenir
    from app.analiz.cikarim import SEMA_AD
    assert SEMA_AD["properties"]["bulgular"]["items"]["properties"]["tur"]["enum"] == ["kisi", "kurum"]
    # Kural bulgularının alıntısı sayfadaki satırın kendisidir
    tarih = next(b for b in sonuc.bulgular if b.deger == "2024-11-03")
    assert SAYFALAR[0][tarih.baslangic:tarih.bitis] == tarih.alinti == "Sözleşme   03.11.2024 tarihinde imzalandı."


def test_uzun_belge_parcalara_bolunur(monkeypatch):
    import app.analiz.cikarim as cikarim

    monkeypatch.setattr(cikarim, "PARCA_KARAKTER", 120)
    model = SahteModel({"bulgular": []}, {"bulgular": []})
    bulgulari_cikar(model, SAYFALAR)
    assert len(model.istemler) == 2
    assert "[SAYFA 2]" in model.istemler[1] and "[SAYFA 1]" not in model.istemler[1]
