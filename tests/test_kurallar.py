"""Kural tabanlı tarih ve tutar çıkarımı testleri (model kullanılmaz). Tüm veriler sentetiktir."""

import pytest

from app.analiz.kurallar import alinti_araligi, tarihleri_bul, tutarlari_bul
from sentetik_veri.analiz_seti import DAVALAR


def _degerler(bulgular):
    return [b.deger for b in bulgular]


@pytest.mark.parametrize("metin, beklenen", [
    ("Sözleşme 03.11.2024 tarihinde imzalandı.", ["2024-11-03"]),
    ("Tarih: 3/11/2024", ["2024-11-03"]),
    ("12 Mart 2025 tarihli yazı", ["2025-03-12"]),
    ("1 ŞUBAT 2019 tarihinden", ["2019-02-01"]),
    ("2020 yılının Mart ayında başladık", ["2020-03"]),
    ("Mart 2020'de başladık", ["2020-03"]),
    ("ISO biçimi 2024-11-03 de olur", ["2024-11-03"]),
    # Tuzaklar: tarih değil
    ("Esas No: 2025/1487 Karar No: 2026/312", []),
    ("Sözleşmenin 4.2. maddesi", []),
    ("Tel: 0212 555 01 23", []),
    ("T.C. Kimlik No: 12345678950", []),
    # Olayın yılı açıkça belirtilmişse yıl düzeyinde tarihtir; "5 yıl" süre değildir
    ("Süre: 5 yıl, 2021 yılında başladı", ["2021"]),
    ("2019 yılından itibaren faiz", ["2019"]),
    ("Kira dönemi 01.01.2024-31.12.2024 arasıdır", ["2024-01-01", "2024-12-31"]),
    ("Teslim 2.11.24 tarihinde", ["2024-11-02"]),
    ("Saat 14:30'da, 6098 sayılı Kanun", []),
    ("Geçersiz 31.13.2024 tarih", []),
])
def test_tarihleri_bul(metin, beklenen):
    assert _degerler(tarihleri_bul(metin)) == beklenen


@pytest.mark.parametrize("metin, beklenen", [
    ("386.420,50 TL alacak", ["386420.50 TRY"]),
    ("borcun 120.000 TL'lik kısmı", ["120000.00 TRY"]),
    ("toplam 386.420,50 TL'nin tahsili", ["386420.50 TRY"]),
    # Rakamla ve yazıyla iki ayrı bahis; analiz aynı değeri tek bulguya indirir
    ("18.000 TL (onsekizbin Türk Lirası)", ["18000.00 TRY", "18000.00 TRY"]),
    ("5.000.-TL asıl alacak, 1.250,75.-TL faiz", ["5000.00 TRY", "1250.75 TRY"]),
    ("7.500-TL ve TL 2.500", ["7500.00 TRY", "2500.00 TRY"]),
    ("USD 3.000 bedel", ["3000.00 USD"]),
    ("1,5 milyon TL ve 250 bin lira", ["1500000.00 TRY", "250000.00 TRY"]),
    ("2 milyon 400 bin TL", ["2400000.00 TRY"]),
    ("12.500 liraya kiraladı", ["12500.00 TRY"]),
    ("Yalnız yüzelli bin TL", ["150000.00 TRY"]),
    ("bir milyon iki yüz bin TL", ["1200000.00 TRY"]),
    ("Tanık on gün sonra geldi", []),
    ("120 m², 450 adet, %20 KDV, 3 taksit", []),
    ("IBAN: TR12 0006 1005 1978 6457 8413 26", []),
    ("Depozito: $2,000", ["2000.00 USD"]),
    ("bedel ₺5.000 olarak", ["5000.00 TRY"]),
    ("1.250,75 EUR ve 300 Avro", ["1250.75 EUR", "300.00 EUR"]),
    ("5.000 Türk Lirası prim", ["5000.00 TRY"]),
    # Tuzaklar: para birimi yok ya da tutar değil
    ("Yıllık faiz oranı %24,5'tir.", []),
    ("Esas No: 2025/1487", []),
    ("14 günlük yıllık izin", []),
    ("Baro sicil no 48213", []),
    ("TLS sertifikası 2048 bit", []),
])
def test_tutarlari_bul(metin, beklenen):
    assert _degerler(tutarlari_bul(metin)) == beklenen


def test_olcum_setindeki_tum_tarih_ve_tutarlar_eksiksiz_ve_fazlasiz_bulunur():
    for dava in DAVALAR:
        for belge in dava.belgeler:
            beklenen = {(t, d) for (t, d) in belge.beklenen() if t in ("tarih", "tutar")}
            bulunan = set()
            for metin in belge.sayfa_metinleri():
                bulunan |= {(b.tur, b.deger) for b in (*tarihleri_bul(metin), *tutarlari_bul(metin))}
            assert bulunan == beklenen, (belge.ad, bulunan ^ beklenen)


def test_alinti_satiri_verir_uzun_satiri_kirpar():
    metin = "Başlık\nDavalıya 17.02.2025 tarihinde ihtarname gönderildi.\nSon satır"
    (b,) = tarihleri_bul(metin)
    bas, bit = alinti_araligi(metin, b.baslangic, b.bitis)
    assert metin[bas:bit] == "Davalıya 17.02.2025 tarihinde ihtarname gönderildi."

    uzun = "kelime " * 80 + "03.11.2024 tarihinde " + "kelime " * 80
    (b,) = tarihleri_bul(uzun)
    bas, bit = alinti_araligi(uzun, b.baslangic, b.bitis, en_fazla=100)
    parca = uzun[bas:bit]
    assert "03.11.2024" in parca and len(parca) <= 110
    assert parca.startswith("kelime") and parca.endswith(("kelime", "tarihinde"))
