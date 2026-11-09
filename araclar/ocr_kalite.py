"""OCR kalite ölçümü: bozulmuş sentetik taramalarla OCR doğruluğunu ölçer.

Bilinen metinli bir mahkeme belgesi sayfası (tamamen uydurma) üretilir, gerçek
taramalarda görülen bozulmalar uygulanır ve sayfa uygulamanın gerçek OCR
yolundan geçirilir (görüntü PDF'e gömülür, pypdfium2 ile yeniden görüntülenir,
Tesseract ile okunur).

Ölçütler:
- KHO (karakter hata oranı): düzenleme uzaklığı / doğru metin uzunluğu. Düşük iyi.
- Alan: tutar, tarih, isim, esas no gibi kritik alanların birebir doğru okunma oranı.
- Güven: Tesseract'ın verdiği ortalama güven skoru.

Çalıştırmak için:
    python araclar/ocr_kalite.py
    python araclar/ocr_kalite.py --on-isleme yok egiklik
"""

import argparse
import io
import sys
import time
from pathlib import Path

import numpy as np
from fpdf import FPDF
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import ayarlar  # noqa: E402
from app.belge import on_isleme  # noqa: E402
from app.belge.ocr import PdfGoruntuleyici, goruntuden_metin  # noqa: E402

# Tamamen uydurma bir dava belgesi
SATIRLAR = [
    "T.C. İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ",
    "Esas No: 2025/1487    Karar No: 2026/312",
    "Davacı: Ayşe Yılmaz",
    "Vekili: Av. Mehmet Öztürk",
    "Davalı: Çağlar Gıda Sanayi ve Ticaret A.Ş.",
    "Dava Değeri: 1.248.750,00 TL",
    "Sözleşme tarihi 03.11.2024 olup ihtarname 17.02.2025 tarihinde tebliğ edilmiştir.",
    "Ödenmeyen fatura bedeli 386.420,50 TL olup yıllık faiz oranı %24,5'tir.",
    "Davalı şirket, 12 Mart 2025 tarihli yazısıyla borcun bir kısmını kabul etmiştir.",
    "Protokolün 4.2. maddesi uyarınca cezai şart 50.000 TL olarak belirlenmiştir.",
    "Tanık İsmail Güneş, ödemenin yapılmadığını beyan etmiştir.",
    "Gereği düşünüldü: Davanın KISMEN KABULÜNE karar verilmiştir.",
]

KRITIK_ALANLAR = {
    "tutar": ["1.248.750,00 TL", "386.420,50 TL", "50.000 TL", "%24,5"],
    "tarih": ["03.11.2024", "17.02.2025", "12 Mart 2025"],
    "isim": ["Ayşe Yılmaz", "Mehmet Öztürk", "Çağlar Gıda", "İsmail Güneş"],
    "no": ["2025/1487", "2026/312", "4.2."],
}

# (dosya, piksel boyutu @ 300 dpi). Courier sabit genişlikli olduğu için 10 punto
# kullanılır; 12 puntoda uzun satırlar sayfa kenarından taşar.
YAZI_TIPLERI = {
    "times": (r"C:\Windows\Fonts\times.ttf", 50),   # 12 punto
    "courier": (r"C:\Windows\Fonts\cour.ttf", 42),  # 10 punto
}

A4_300DPI = (2480, 3508)


def sayfa_uret(yazi_tipi: tuple[str, int]) -> Image.Image:
    font_yolu, boyut = yazi_tipi
    goruntu = Image.new("L", A4_300DPI, color=255)
    cizim = ImageDraw.Draw(goruntu)
    font = ImageFont.truetype(font_yolu, boyut)
    # Satır sayfaya sığmıyorsa ölçüm geçersiz olur
    assert all(cizim.textlength(s, font=font) < A4_300DPI[0] - 2 * 220 for s in SATIRLAR)
    for i, satir in enumerate(SATIRLAR):
        cizim.text((220, 300 + i * 85), satir, fill=0, font=font)
    return goruntu


# --- Bozulmalar (300 dpi gri görüntü alır, "taranmış" görüntü döndürür) ---

def _rng():
    return np.random.default_rng(42)


def _dondur(g, aci):
    return g.rotate(aci, resample=Image.BICUBIC, fillcolor=255)


def _dpi(g, dpi):
    w, h = g.size
    return g.resize((int(w * dpi / 300), int(h * dpi / 300)), Image.LANCZOS)


def _gurultu(g, sigma, tuz_biber=0.0):
    a = np.asarray(g, dtype=np.float32)
    rng = _rng()
    a = a + rng.normal(0, sigma, a.shape)
    if tuz_biber:
        maske = rng.random(a.shape)
        a[maske < tuz_biber / 2] = 0
        a[maske > 1 - tuz_biber / 2] = 255
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def _jpeg(g, kalite):
    tampon = io.BytesIO()
    g.save(tampon, format="JPEG", quality=kalite)
    return Image.open(io.BytesIO(tampon.getvalue())).convert("L")


def _soluk(g):
    # Mürekkep 150, kâğıt 230 civarı: soluk fotokopi
    a = np.asarray(g, dtype=np.float32)
    return Image.fromarray((150 + a * (80 / 255)).astype(np.uint8))


def _golge(g):
    # Telefonla çekilmiş sayfa: bir kenardan diğerine düzensiz aydınlatma
    a = np.asarray(g, dtype=np.float32)
    w = a.shape[1]
    egim = np.linspace(1.0, 0.45, w)[None, :]
    return Image.fromarray(np.clip(a * egim, 0, 255).astype(np.uint8))


def _faks(g):
    # Standart faks çözünürlüğü (204x98 dpi), ikili görüntü, lekeler
    w, h = g.size
    k = g.resize((int(w * 204 / 300), int(h * 98 / 300)), Image.LANCZOS)
    a = np.asarray(k) > 150
    rng = _rng()
    a[rng.random(a.shape) < 0.003] = False
    return Image.fromarray((a * 255).astype(np.uint8))


BOZULMALAR = {
    "temiz": lambda g: g,
    "egik_1.5": lambda g: _dondur(g, 1.5),
    "egik_4": lambda g: _dondur(g, 4),
    "dpi_150": lambda g: _dpi(g, 150),
    "dpi_100": lambda g: _dpi(g, 100),
    "gurultu": lambda g: _gurultu(g, 35, tuz_biber=0.01),
    "bulanik": lambda g: g.filter(ImageFilter.GaussianBlur(2.2)),
    "jpeg_15": lambda g: _jpeg(g, 15),
    "soluk": _soluk,
    "golge": _golge,
    "faks": _faks,
    "kombine": lambda g: _jpeg(_gurultu(_dpi(_dondur(g, 2.5), 150), 20), 30),
}


# --- Ölçüm --------------------------------------------------

def _duzle(metin: str) -> str:
    return " ".join(metin.split())


def duzenleme_uzakligi(a: str, b: str) -> int:
    onceki = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        simdiki = [i]
        for j, cb in enumerate(b, 1):
            simdiki.append(min(onceki[j] + 1, simdiki[j - 1] + 1, onceki[j - 1] + (ca != cb)))
        onceki = simdiki
    return onceki[-1]


def ocr_et(taranmis: Image.Image, on_isle: str) -> tuple[str, float | None]:
    """Uygulamadaki yolu taklit eder: görüntü PDF'e gömülür, 300 dpi'da yeniden görüntülenir."""
    pdf = FPDF()
    pdf.add_page()
    pdf.image(taranmis, x=0, y=0, w=210, h=297)
    with PdfGoruntuleyici(bytes(pdf.output())) as g:
        sayfa = g.sayfa(1, 300)
    islenmis = on_isleme.isle(on_isle, sayfa)
    return goruntuden_metin(islenmis.goruntu, islenmis.dikey_cizgi_var)


def olc(on_isle_adi: str) -> list[dict]:
    on_isle = on_isle_adi
    dogru = _duzle("\n".join(SATIRLAR))
    sonuclar = []
    for font_adi, yazi_tipi in YAZI_TIPLERI.items():
        temiz = sayfa_uret(yazi_tipi)
        for bozulma_adi, boz in BOZULMALAR.items():
            baslangic = time.perf_counter()
            metin, guven = ocr_et(boz(temiz), on_isle)
            sure = time.perf_counter() - baslangic
            okunan = _duzle(metin)
            alanlar = {
                tur: sum(deger in okunan for deger in degerler) / len(degerler)
                for tur, degerler in KRITIK_ALANLAR.items()
            }
            tum = [d for ds in KRITIK_ALANLAR.values() for d in ds]
            sonuclar.append({
                "on_isleme": on_isle_adi,
                "font": font_adi,
                "bozulma": bozulma_adi,
                "kho": duzenleme_uzakligi(okunan, dogru) / len(dogru),
                "alan": sum(d in okunan for d in tum) / len(tum),
                "alanlar": alanlar,
                "kacirilan": [d for d in tum if d not in okunan],
                "guven": guven,
                "sure": sure,
            })
    return sonuclar


def main():
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--on-isleme", nargs="+", default=list(on_isleme.YONTEMLER))
    ayristirici.add_argument("--psm", help="Tesseract sayfa bölütleme kipi (varsayılan: ayarlardaki)")
    ayristirici.add_argument("--json", help="Ham sonuçların yazılacağı dosya")
    secenekler = ayristirici.parse_args()
    if secenekler.psm:
        ayarlar.OCR_PSM = secenekler.psm
    print(f"PSM: {ayarlar.OCR_PSM}")

    tum = []
    for ad in secenekler.on_isleme:
        sonuclar = olc(ad)
        tum.extend(sonuclar)
        print(f"\n## Ön işleme: {ad}\n")
        print("| bozulma | font | KHO | alan | güven | süre | kaçırılan |")
        print("|---|---|---|---|---|---|---|")
        for s in sonuclar:
            guven = f"{s['guven']:.2f}" if s["guven"] is not None else "-"
            print(f"| {s['bozulma']} | {s['font']} | {s['kho']:.1%} | {s['alan']:.0%} | {guven} | "
                  f"{s['sure']:.1f} sn | {', '.join(s['kacirilan'])} |")
        ort_kho = sum(s["kho"] for s in sonuclar) / len(sonuclar)
        ort_alan = sum(s["alan"] for s in sonuclar) / len(sonuclar)
        print(f"\nOrtalama KHO: {ort_kho:.1%}  ortalama alan doğruluğu: {ort_alan:.0%}")

    if secenekler.json:
        import json
        Path(secenekler.json).write_text(json.dumps(tum, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
