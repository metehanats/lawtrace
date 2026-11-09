"""Analiz ölçümü: sentetik dava setinde bir modelin bulgu çıkarma başarısı.

OCR bu ölçüme dahil değildir: belgeler doğrudan metin olarak verilir (OCR ayrıca
araclar/ocr_kalite.py ile ölçülüyor). Tüm veriler uydurmadır.

Ölçütler (bulgu türü başına):
- Kesinlik: modelin bulduğu (doğrulamadan geçen) bulguların ne kadarı beklenen listede.
  Düşük kesinlik = uydurma ya da gereksiz bulgu.
- Duyarlılık: beklenen bulguların ne kadarını buldu.
- Sayfa doğruluğu: doğru bulguların ne kadarı doğru sayfaya bağlandı.
Ayrıca kaynak doğrulamasında reddedilen bulgular nedenleriyle listelenir.

    python araclar/analiz_olcum.py --model qwen3.5:4b
    python araclar/analiz_olcum.py --model qwen3.5:4b --ayrinti   # yanlış ve eksik bulguları yazdırır
"""

import argparse
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "sentetik_veri"))

from analiz_seti import DAVALAR  # noqa: E402

from app.analiz.cikarim import TURLER, adlar_esit, bulgulari_cikar  # noqa: E402
from app.analiz.modeller import OllamaModeli  # noqa: E402


def esles(tur: str, bulunan: str, beklenen: str) -> bool:
    if tur in ("kisi", "kurum"):
        return adlar_esit(bulunan, beklenen)
    return bulunan == beklenen


def belgeyi_olc(model, belge) -> dict:
    sayfalar = belge.sayfa_metinleri()
    beklenen = belge.beklenen()                     # (tür, değer) -> sayfalar
    baslangic = time.perf_counter()
    sonuc = bulgulari_cikar(model, sayfalar)
    sure = time.perf_counter() - baslangic

    # Aynı (tür, değer) farklı sayfalarda bulunduysa bir kez sayılır (beklenenle aynı birim)
    bulunan: dict[tuple[str, str], set[int]] = defaultdict(set)
    for b in sonuc.bulgular:
        bulunan[(b.tur, b.deger)].add(b.sayfa_no)

    dp, yp, ye = Counter(), [], []                  # doğru, yanlış pozitif, eksik
    sayfa_dogru = Counter()
    eslesen_beklenen = set()
    for (tur, deger), sayfalar_b in bulunan.items():
        hedef = next((k for k in beklenen if k[0] == tur and k not in eslesen_beklenen and esles(tur, deger, k[1])),
                     None)
        if hedef is None:
            yp.append((tur, deger, sorted(sayfalar_b)))
            continue
        eslesen_beklenen.add(hedef)
        dp[tur] += 1
        if sayfalar_b & beklenen[hedef]:
            sayfa_dogru[tur] += 1
    for k, s in beklenen.items():
        if k not in eslesen_beklenen:
            ye.append((k[0], k[1], sorted(s)))
    return {"belge": belge.ad, "dp": dp, "yp": yp, "ye": ye, "sayfa_dogru": sayfa_dogru,
            "reddedilen": sonuc.reddedilen, "sure": sure}


def main():
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--model", default="qwen3.5:4b")
    ayristirici.add_argument("--ayrinti", action="store_true")
    ayristirici.add_argument("--baglam", type=int, default=8192, help="Modelin bağlam penceresi (token)")
    ayristirici.add_argument("--parca", type=int, default=None, help="Bir çağrıya verilecek en fazla karakter")
    s = ayristirici.parse_args()
    model = OllamaModeli(s.model, baglam=s.baglam)
    if s.parca:
        import app.analiz.cikarim as cikarim
        cikarim.PARCA_KARAKTER = s.parca
    print(f"Bağlam: {s.baglam} token, parça: {s.parca or 'varsayılan'} karakter")

    toplam = {"dp": Counter(), "yp": Counter(), "ye": Counter(), "sayfa": Counter()}
    reddedilen = Counter()
    sure = 0.0
    print(f"Model: {model.saglayici}/{model.model}\n")
    for dava in DAVALAR:
        for belge in dava.belgeler:
            r = belgeyi_olc(model, belge)
            sure += r["sure"]
            for tur in TURLER:
                toplam["dp"][tur] += r["dp"][tur]
                toplam["sayfa"][tur] += r["sayfa_dogru"][tur]
            for tur, *_ in r["yp"]:
                toplam["yp"][tur] += 1
            for tur, *_ in r["ye"]:
                toplam["ye"][tur] += 1
            for _, neden in r["reddedilen"]:
                reddedilen[neden] += 1
            print(f"- {dava.ad} / {belge.ad}: {sum(r['dp'].values())} doğru, {len(r['yp'])} yanlış, "
                  f"{len(r['ye'])} eksik, {len(r['reddedilen'])} reddedildi · {r['sure']:.1f} sn")
            if s.ayrinti:
                for tur, deger, sayfalar in r["yp"]:
                    print(f"    YANLIŞ  {tur:6} {deger}  (sayfa {sayfalar})")
                for tur, deger, sayfalar in r["ye"]:
                    print(f"    EKSİK   {tur:6} {deger}  (sayfa {sayfalar})")
                for ham, neden in r["reddedilen"]:
                    print(f"    RED     {neden}: {ham.get('tur')} {ham.get('deger')!r} ← {ham.get('alinti')!r}")

    print("\n| tür | kesinlik | duyarlılık | doğru | yanlış | eksik | doğru sayfa |")
    print("|---|---|---|---|---|---|---|")
    for tur in (*TURLER, "TOPLAM"):
        if tur == "TOPLAM":
            dp, yp, ye, sd = (sum(toplam[k].values()) for k in ("dp", "yp", "ye", "sayfa"))
        else:
            dp, yp, ye, sd = toplam["dp"][tur], toplam["yp"][tur], toplam["ye"][tur], toplam["sayfa"][tur]
        kes = dp / (dp + yp) if dp + yp else 0
        duy = dp / (dp + ye) if dp + ye else 0
        print(f"| {tur} | {kes:.0%} | {duy:.0%} | {dp} | {yp} | {ye} | {sd}/{dp} |")
    print(f"\nReddedilen (kaynak doğrulaması): {dict(reddedilen) or 'yok'}")
    print(f"Toplam süre: {sure:.0f} sn")


if __name__ == "__main__":
    main()
