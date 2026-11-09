"""Sayfa düzeni ölçümü: çok sütunlu, tablolu ve iki bloklu başlıklı sayfalarda OCR.

ocr_kalite.py tek sütunlu metni ölçer. Bu betik, satırların doğru sırada ve
doğru gruplanarak okunup okunmadığını ölçer. Bir tabloda tarihin yanlış tutarla
aynı satıra düşmesi, metin harf harf doğru olsa bile yanlış bulguya yol açar.

Ölçütler:
- Satır doğruluğu: her doğru satır için (tabloda her satırın hücreleri yan yana),
  OCR çıktısında ona en az %90 benzeyen bir satır var mı? Sütunların birbirine
  karışması (sol sütunun satırıyla sağ sütunun satırının birleşmesi) ya da bir
  satırın bölünmesi bu oranı düşürür.
- KHO: okuma sırasına göre (önce sol sütun, sonra sağ; tabloda satır satır)
  karakter hata oranı.
- Alan: kritik değerlerin birebir okunma oranı.

Çalıştırmak için:
    python araclar/ocr_duzen.py --psm 3 4 6
"""

import argparse
import difflib
import sys
from dataclasses import dataclass, field
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_kalite import A4_300DPI, BOZULMALAR, _duzle, duzenleme_uzakligi, ocr_et  # noqa: E402

from app import ayarlar  # noqa: E402
from app.belge import on_isleme  # noqa: E402

FONT = r"C:\Windows\Fonts\times.ttf"
FONT_KALIN = r"C:\Windows\Fonts\timesbd.ttf"
BOYUT = 46
SATIR = 72
KENAR = 200


@dataclass
class Duzen:
    goruntu: Image.Image
    satirlar: list[str]                   # okuma sırasıyla doğru satırlar
    alanlar: list[str] = field(default_factory=list)


def _cizici():
    g = Image.new("L", A4_300DPI, color=255)
    return g, ImageDraw.Draw(g), ImageFont.truetype(FONT, BOYUT), ImageFont.truetype(FONT_KALIN, BOYUT)


def _sigiyor(cizim, metin, font, genislik):
    assert cizim.textlength(metin, font=font) <= genislik, metin


SOL_SUTUN = ("DAVACI TARAFIN İDDİALARI",
             "Davacı, davalıya 03.11.2024 tarihinde sözleşme uyarınca mal teslim etmiştir. "
             "Teslim edilen malların bedeli olan 386.420,50 TL bugüne kadar ödenmemiştir. "
             "Davalıya 17.02.2025 tarihinde ihtarname gönderilmiş, ancak sonuç alınamamıştır. "
             "Tanık Hüseyin Aksoy teslimatı görmüştür. Davacı, alacağın yıllık %24,5 faiziyle "
             "birlikte tahsilini talep etmektedir.")
SAG_SUTUN = ("DAVALI TARAFIN SAVUNMASI",
             "Davalı, malların ayıplı olduğunu ve 08.12.2024 tarihli tutanakla bunun tespit "
             "edildiğini ileri sürmektedir. Davalıya göre borç en fazla 120.000 TL olup kalan "
             "kısım için takas yapılmıştır. Tanık Zeynep Karaca ayıbı doğrulamıştır. Davalı, "
             "12 Mart 2025 tarihli yazısında borcun bir kısmını kabul etmiş değildir. Davanın "
             "reddi talep edilmektedir.")


def _kaydir(cizim, metin, font, genislik) -> list[str]:
    """Metni sütun genişliğine göre satırlara böler (gerçek belgelerdeki gibi)."""
    satirlar, satir = [], ""
    for kelime in metin.split():
        aday = f"{satir} {kelime}".strip()
        if cizim.textlength(aday, font=font) <= genislik:
            satir = aday
        else:
            satirlar.append(satir)
            satir = kelime
    return satirlar + [satir]


def iki_sutun(bosluk: int = 90) -> Duzen:
    g, c, f, fk = _cizici()
    ust = "T.C. ANKARA 3. ASLİYE TİCARET MAHKEMESİ - Esas No: 2025/2210"
    c.text((KENAR, 250), ust, font=fk, fill=0)
    genislik = (A4_300DPI[0] - 2 * KENAR - bosluk) // 2
    dogru = [ust]
    for (baslik, govde), x in ((SOL_SUTUN, KENAR), (SAG_SUTUN, KENAR + genislik + bosluk)):
        satirlar = [baslik] + _kaydir(c, govde, f, genislik)
        for i, satir in enumerate(satirlar):
            c.text((x, 400 + i * SATIR), satir, font=fk if i == 0 else f, fill=0)
        dogru += satirlar
    return Duzen(g, dogru,
                 ["386.420,50 TL", "120.000 TL", "03.11.2024", "17.02.2025", "08.12.2024",
                  "12 Mart 2025", "%24,5", "Hüseyin Aksoy", "Zeynep Karaca", "2025/2210"])


TABLO = [
    ("Tarih", "Fatura No", "Açıklama", "Tutar"),
    ("03.11.2024", "F-2024/118", "Mal bedeli", "120.000,00 TL"),
    ("15.11.2024", "F-2024/131", "Nakliye", "8.750,00 TL"),
    ("02.12.2024", "F-2024/140", "Mal bedeli", "214.300,50 TL"),
    ("19.12.2024", "F-2024/152", "Montaj hizmeti", "31.120,00 TL"),
    ("07.01.2025", "F-2025/004", "Yedek parça", "12.250,00 TL"),
    ("", "", "TOPLAM", "386.420,50 TL"),
]


def tablo(cizgili: bool) -> Duzen:
    g, c, f, fk = _cizici()
    baslik = "EK-3: Ödenmeyen faturalar listesi"
    c.text((KENAR, 250), baslik, font=fk, fill=0)
    sutun_x = [KENAR, KENAR + 420, KENAR + 850, KENAR + 1500, A4_300DPI[0] - KENAR]
    ust = 380
    yukseklik = 95
    for i, satir in enumerate(TABLO):
        y = ust + i * yukseklik
        for j, hucre in enumerate(satir):
            font = fk if i == 0 or hucre == "TOPLAM" else f
            _sigiyor(c, hucre, font, sutun_x[j + 1] - sutun_x[j] - 40)
            if j == 3 and i > 0:
                # Tutarlar sağa yaslı
                x = sutun_x[j + 1] - 20 - c.textlength(hucre, font=font)
            else:
                x = sutun_x[j] + 20
            c.text((x, y + 20), hucre, font=font, fill=0)
    if cizgili:
        alt = ust + len(TABLO) * yukseklik
        for i in range(len(TABLO) + 1):
            c.line([(sutun_x[0], ust + i * yukseklik), (sutun_x[-1], ust + i * yukseklik)], fill=0, width=3)
        for x in sutun_x:
            c.line([(x, ust), (x, alt)], fill=0, width=3)
    satirlar = [baslik] + [" ".join(h for h in s if h) for s in TABLO]
    return Duzen(g, satirlar,
                 ["120.000,00 TL", "8.750,00 TL", "214.300,50 TL", "31.120,00 TL", "12.250,00 TL",
                  "386.420,50 TL", "F-2024/118", "F-2025/004", "07.01.2025"])


DELIL_TABLOSU = [
    ("Delil", "Açıklama"),
    ("Satış sözleşmesi aslı", "Taraflarca imzalanmış, 03.11.2024 tarihli"),
    ("Teslim tutanağı ve irsaliye", "Malların eksiksiz teslim edildiğini gösterir"),
    ("Banka hesap dökümü", "386.420,50 TL ödemenin yapılmadığını gösterir"),
    ("Tanık Hüseyin Aksoy beyanı", "Teslimat sırasında depoda bulunmuştur"),
]


def delil_tablosu(cizgili: bool, siki: bool = False) -> Duzen:
    """İki sütunu da düzyazı olan tablo: sütun ayırma bunu iki sütunlu metin sanmamalı.

    siki=True: sütun genişliği en uzun hücreye göre ayarlanır ("içeriğe sığdır"),
    böylece hücre ile sütun sınırı arasındaki boşluk iki sütunlu metindeki kadar dar olur.
    """
    g, c, f, fk = _cizici()
    baslik = "DELİLLER"
    c.text((KENAR, 250), baslik, font=fk, fill=0)
    if siki:
        en_uzun = max(c.textlength(s[0], font=f) for s in DELIL_TABLOSU)
        sutun_x = [KENAR, KENAR + int(en_uzun) + 60, A4_300DPI[0] - KENAR]
    else:
        sutun_x = [KENAR, KENAR + 900, A4_300DPI[0] - KENAR]
    ust, yukseklik = 380, 95
    for i, satir in enumerate(DELIL_TABLOSU):
        for j, hucre in enumerate(satir):
            font = fk if i == 0 else f
            _sigiyor(c, hucre, font, sutun_x[j + 1] - sutun_x[j] - 40)
            c.text((sutun_x[j] + 20, ust + i * yukseklik + 20), hucre, font=font, fill=0)
    if cizgili:
        alt = ust + len(DELIL_TABLOSU) * yukseklik
        for i in range(len(DELIL_TABLOSU) + 1):
            c.line([(sutun_x[0], ust + i * yukseklik), (sutun_x[-1], ust + i * yukseklik)], fill=0, width=3)
        for x in sutun_x:
            c.line([(x, ust), (x, alt)], fill=0, width=3)
    return Duzen(g, [baslik] + [" ".join(s) for s in DELIL_TABLOSU],
                 ["03.11.2024", "386.420,50 TL", "Hüseyin Aksoy"])


def iki_bloklu_baslik() -> Duzen:
    """İhtarname/dilekçe başı: solda büro bilgisi, sağda tarih ve sayı, altında tek sütun metin."""
    g, c, f, fk = _cizici()
    sol = ["Av. Selin Demirtaş Hukuk Bürosu", "Kızılay Mah. Atatürk Blv. No: 41/7", "Çankaya / ANKARA"]
    sag = ["Tarih: 21.01.2025", "Sayı: 2025/014", "Konu: İhtarname"]
    for i, s in enumerate(sol):
        c.text((KENAR, 250 + i * SATIR), s, font=fk if i == 0 else f, fill=0)
    for i, s in enumerate(sag):
        x = A4_300DPI[0] - KENAR - c.textlength(s, font=f)
        c.text((x, 250 + i * SATIR), s, font=f, fill=0)
    govde = [
        "Muhatap: Çağlar Gıda Sanayi ve Ticaret A.Ş.",
        "Müvekkilimize ait 386.420,50 TL tutarındaki alacağın, işbu ihtarnamenin",
        "tebliğinden itibaren 7 gün içinde ödenmesini, aksi halde yasal yollara",
        "başvurulacağını ihtaren bildiririz.",
    ]
    for i, s in enumerate(govde):
        c.text((KENAR, 600 + i * SATIR), s, font=f, fill=0)
    # Okuma sırası: önce sol blok, sonra sağ blok, sonra gövde
    return Duzen(g, sol + sag + govde,
                 ["21.01.2025", "2025/014", "386.420,50 TL", "Selin Demirtaş", "Çağlar Gıda"])


def tek_sutun() -> Duzen:
    """Karşılaştırma için: düz metin sayfası (PSM 4'ün bunu bozmadığını görmek için)."""
    g, c, f, fk = _cizici()
    satirlar = [
        "T.C. İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ",
        "Esas No: 2025/1487",
        "Davacı: Ayşe Yılmaz",
        "Davalı: Çağlar Gıda Sanayi ve Ticaret A.Ş.",
        "Ödenmeyen fatura bedeli 386.420,50 TL olup yıllık faiz oranı %24,5'tir.",
        "Davalı şirket, 12 Mart 2025 tarihli yazısıyla borcun bir kısmını kabul etmiştir.",
    ]
    for i, s in enumerate(satirlar):
        c.text((KENAR, 250 + i * SATIR), s, font=f, fill=0)
    return Duzen(g, satirlar, ["386.420,50 TL", "%24,5", "12 Mart 2025", "Ayşe Yılmaz", "2025/1487"])


UC_SUTUN = [
    ("DAVACI BEYANI",
     "Davacı, aracın 14.06.2024 tarihinde kavşakta durduğunu ve davalının arkadan çarptığını "
     "beyan etmiştir. Onarım bedeli olarak 84.300 TL talep edilmektedir."),
    ("DAVALI BEYANI",
     "Davalı, davacının ani fren yaptığını ve kusurun paylaşılması gerektiğini ileri sürmüştür. "
     "Sigorta şirketi 27.06.2024 tarihinde 41.000 TL ödemiştir."),
    ("TANIK BEYANI",
     "Tanık Elif Şahin, ışığın kırmızı yandığını ve davacının durmuş olduğunu görmüştür. "
     "Olay saati yaklaşık 18.40 olarak belirtilmiştir."),
]


def uc_sutun(bosluk: int = 70) -> Duzen:
    """Üç sütunlu karşılaştırma sayfası (bilirkişi raporlarında taraf beyanları yan yana)."""
    g, c, f, fk = _cizici()
    ust = "BİLİRKİŞİ RAPORU - Taraf beyanlarının karşılaştırılması"
    c.text((KENAR, 250), ust, font=fk, fill=0)
    genislik = (A4_300DPI[0] - 2 * KENAR - 2 * bosluk) // 3
    dogru = [ust]
    for n, (baslik, govde) in enumerate(UC_SUTUN):
        x = KENAR + n * (genislik + bosluk)
        satirlar = [baslik] + _kaydir(c, govde, f, genislik)
        for i, satir in enumerate(satirlar):
            c.text((x, 400 + i * SATIR), satir, font=fk if i == 0 else f, fill=0)
        dogru += satirlar
    return Duzen(g, dogru, ["14.06.2024", "84.300 TL", "27.06.2024", "41.000 TL", "Elif Şahin", "18.40"])


GENIS_TABLO = [
    ("Sıra", "Tarih", "Belge No", "Açıklama", "KDV", "Tutar"),
    ("1", "03.11.2024", "F-118", "Mal bedeli", "20.000,00", "120.000,00"),
    ("2", "15.11.2024", "F-131", "Nakliye", "1.458,33", "8.750,00"),
    ("3", "02.12.2024", "F-140", "Mal bedeli", "35.716,75", "214.300,50"),
    ("4", "19.12.2024", "F-152", "Montaj", "5.186,67", "31.120,00"),
    ("5", "07.01.2025", "F-004", "Yedek parça", "2.041,67", "12.250,00"),
    ("6", "21.01.2025", "F-019", "Servis", "1.250,00", "7.500,00"),
]
SUTUN_GENISLIKLERI = [130, 330, 250, 480, 300, 330]


def _tablo_ciz(c, f, fk, satirlar, ust, baslik_var: bool, cizgili: bool, yukseklik: int = 95):
    sutun_x = [KENAR]
    for w in SUTUN_GENISLIKLERI:
        sutun_x.append(sutun_x[-1] + w)
    for i, satir in enumerate(satirlar):
        y = ust + i * yukseklik
        for j, hucre in enumerate(satir):
            font = fk if (baslik_var and i == 0) or hucre == "TOPLAM" else f
            _sigiyor(c, hucre, font, sutun_x[j + 1] - sutun_x[j] - 30)
            # Sayılar sağa yaslı
            if j >= 4 and not (baslik_var and i == 0):
                x = sutun_x[j + 1] - 15 - c.textlength(hucre, font=font)
            else:
                x = sutun_x[j] + 15
            c.text((x, y + 20), hucre, font=font, fill=0)
    if cizgili:
        alt = ust + len(satirlar) * yukseklik
        for i in range(len(satirlar) + 1):
            c.line([(sutun_x[0], ust + i * yukseklik), (sutun_x[-1], ust + i * yukseklik)], fill=0, width=3)
        for x in sutun_x:
            c.line([(x, ust), (x, alt)], fill=0, width=3)
    return ust + len(satirlar) * yukseklik


def genis_tablo(cizgili: bool) -> Duzen:
    """Altı sütunlu fatura dökümü: her satır bütün okunmalı (tarih ile tutar aynı satırda)."""
    g, c, f, fk = _cizici()
    baslik = "EK-4: Fatura dökümü (KDV dahil)"
    c.text((KENAR, 250), baslik, font=fk, fill=0)
    _tablo_ciz(c, f, fk, GENIS_TABLO, 380, True, cizgili)
    return Duzen(g, [baslik] + [" ".join(s) for s in GENIS_TABLO],
                 ["03.11.2024", "120.000,00", "35.716,75", "214.300,50", "21.01.2025", "7.500,00", "F-152"])


DEVAM_SATIRLARI = [
    ("7", "04.02.2025", "F-031", "Mal bedeli", "9.833,33", "59.000,00"),
    ("8", "18.02.2025", "F-044", "Nakliye", "1.083,33", "6.500,00"),
    ("9", "03.03.2025", "F-052", "Montaj", "2.200,00", "13.200,00"),
    ("", "", "", "TOPLAM", "79.270,08", "478.620,50"),
]


def tablo_devam(cizgili: bool) -> Duzen:
    """Önceki sayfadan taşan tablo: sayfa başlıksız satırlarla başlar, TOPLAM'dan sonra düzyazı gelir."""
    g, c, f, fk = _cizici()
    alt = _tablo_ciz(c, f, fk, DEVAM_SATIRLARI, 250, False, cizgili)
    govde = [
        "Yukarıdaki dökümde yer alan faturaların toplam bedeli 478.620,50 TL olup davalı",
        "tarafından bugüne kadar herhangi bir ödeme yapılmamıştır. Faturalar davalıya",
        "süresi içinde tebliğ edilmiş ve itiraz edilmemiştir.",
    ]
    for i, s in enumerate(govde):
        c.text((KENAR, alt + 120 + i * SATIR), s, font=f, fill=0)
    return Duzen(g, [" ".join(h for h in s if h) for s in DEVAM_SATIRLARI] + govde,
                 ["04.02.2025", "59.000,00", "13.200,00", "478.620,50", "79.270,08", "478.620,50 TL"])


DUZENLER = {
    "tek_sutun": tek_sutun,
    "iki_sutun": iki_sutun,
    "iki_sutun_genis_bosluk": lambda: iki_sutun(bosluk=180),
    "tablo_cizgili": lambda: tablo(True),
    "tablo_cizgisiz": lambda: tablo(False),
    "delil_tablosu_cizgili": lambda: delil_tablosu(True),
    "delil_tablosu_cizgisiz": lambda: delil_tablosu(False),
    "delil_tablosu_siki_cizgili": lambda: delil_tablosu(True, siki=True),
    "delil_tablosu_siki_cizgisiz": lambda: delil_tablosu(False, siki=True),
    "iki_bloklu_baslik": iki_bloklu_baslik,
    "uc_sutun": uc_sutun,
    "uc_sutun_genis_bosluk": lambda: uc_sutun(bosluk=140),
    "genis_tablo_cizgili": lambda: genis_tablo(True),
    "genis_tablo_cizgisiz": lambda: genis_tablo(False),
    "tablo_devam_cizgili": lambda: tablo_devam(True),
    "tablo_devam_cizgisiz": lambda: tablo_devam(False),
}

SECILI_BOZULMALAR = ["temiz", "egik_1.5", "dpi_150", "kombine"]


def satir_dogrulugu(dogru: list[str], metin: str, esik: float = 0.9) -> tuple[float, list[str]]:
    okunan = [_duzle(s) for s in metin.splitlines() if s.strip()]
    kacan = []
    for satir in dogru:
        hedef = _duzle(satir)
        en_iyi = max((difflib.SequenceMatcher(None, hedef, o).ratio() for o in okunan), default=0)
        if en_iyi < esik:
            kacan.append(satir)
    return 1 - len(kacan) / len(dogru), kacan


def olc(psm: str, on_isle_adi: str, ayrinti: bool) -> list[dict]:
    ayarlar.OCR_PSM = psm
    on_isle = on_isle_adi
    sonuclar = []
    for duzen_adi, uret in DUZENLER.items():
        duzen = uret()
        for bozulma in SECILI_BOZULMALAR:
            metin, guven = ocr_et(BOZULMALAR[bozulma](duzen.goruntu), on_isle)
            dogru_metin = _duzle(" ".join(duzen.satirlar))
            satir, kacan = satir_dogrulugu(duzen.satirlar, metin)
            okunan = _duzle(metin)
            s = {
                "psm": psm, "duzen": duzen_adi, "bozulma": bozulma,
                "satir": satir,
                "kho": duzenleme_uzakligi(okunan, dogru_metin) / len(dogru_metin),
                "alan": sum(a in okunan for a in duzen.alanlar) / len(duzen.alanlar),
                "guven": guven, "kacan": kacan, "metin": metin,
            }
            sonuclar.append(s)
            if ayrinti and bozulma == "temiz":
                print(f"\n--- PSM {psm} / {duzen_adi} / temiz ---\n{metin}\n")
    return sonuclar


def main():
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--psm", nargs="+", default=["3", "4", "6"])
    ayristirici.add_argument("--on-isleme", default=ayarlar.OCR_ON_ISLEME)
    ayristirici.add_argument("--ayrinti", action="store_true", help="Temiz sayfaların ham OCR çıktısını yazdır")
    ayristirici.add_argument("--duzen", nargs="+", help="Yalnızca bu düzenleri ölç (ör. uc_sutun genis_tablo_cizgili)")
    secenekler = ayristirici.parse_args()
    if secenekler.duzen:
        for ad in list(DUZENLER):
            if ad not in secenekler.duzen:
                del DUZENLER[ad]

    print(f"Dil: {ayarlar.OCR_DILLERI}, ön işleme: {secenekler.on_isleme}")
    ozet = {}
    for psm in secenekler.psm:
        sonuclar = olc(psm, secenekler.on_isleme, secenekler.ayrinti)
        print(f"\n## PSM {psm}\n")
        print("| düzen | bozulma | satır | KHO | alan | güven |")
        print("|---|---|---|---|---|---|")
        for s in sonuclar:
            g = f"{s['guven']:.2f}" if s["guven"] is not None else "-"
            print(f"| {s['duzen']} | {s['bozulma']} | {s['satir']:.0%} | {s['kho']:.1%} | {s['alan']:.0%} | {g} |")
        for duzen in DUZENLER:
            alt = [s for s in sonuclar if s["duzen"] == duzen]
            ozet[(psm, duzen)] = (
                sum(s["satir"] for s in alt) / len(alt),
                sum(s["kho"] for s in alt) / len(alt),
                sum(s["alan"] for s in alt) / len(alt),
            )

    print("\n## Özet (bozulmaların ortalaması): satır / KHO / alan\n")
    print("| düzen | " + " | ".join(f"PSM {p}" for p in secenekler.psm) + " |")
    print("|---|" + "---|" * len(secenekler.psm))
    for duzen in DUZENLER:
        hucreler = [f"{ozet[(p, duzen)][0]:.0%} / {ozet[(p, duzen)][1]:.1%} / {ozet[(p, duzen)][2]:.0%}"
                    for p in secenekler.psm]
        print(f"| {duzen} | " + " | ".join(hucreler) + " |")


if __name__ == "__main__":
    main()
