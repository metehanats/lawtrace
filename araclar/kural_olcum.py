"""Kural tabanlı tarih ve tutar çıkarımını zor sentetik sette ölçer (model kullanılmaz).

    python araclar/kural_olcum.py            # geliştirme + saklı set
    python araclar/kural_olcum.py --ayrinti  # yanlış ve eksik bulguları yazdırır
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "sentetik_veri"))

from analiz_zor_set import GELISTIRME, SAKLI  # noqa: E402

from app.analiz.kurallar import tarihleri_bul, tutarlari_bul  # noqa: E402


def olc(belgeler, ayrinti: bool) -> dict:
    sonuc = {"tarih": [0, 0, 0], "tutar": [0, 0, 0]}   # doğru, yanlış, eksik
    for belge in belgeler:
        beklenen = set(belge.beklenen())
        bulunan = set()
        for metin in belge.sayfa_metinleri():
            bulunan |= {(b.tur, b.deger) for b in (*tarihleri_bul(metin), *tutarlari_bul(metin))}
        for tur in sonuc:
            b = {x for x in beklenen if x[0] == tur}
            f = {x for x in bulunan if x[0] == tur}
            sonuc[tur][0] += len(b & f)
            sonuc[tur][1] += len(f - b)
            sonuc[tur][2] += len(b - f)
        if ayrinti:
            for x in sorted(bulunan - beklenen):
                print(f"    [{belge.ad}] YANLIŞ {x}")
            for x in sorted(beklenen - bulunan):
                yazilis = belge.yazilislar()[x]
                print(f"    [{belge.ad}] EKSİK  {x}  ← {sorted(yazilis)}")
    return sonuc


def tablo(ad: str, sonuc: dict) -> None:
    print(f"\n{ad}\n| tür | kesinlik | duyarlılık | doğru | yanlış | eksik |\n|---|---|---|---|---|---|")
    for tur, (d, y, e) in [*sonuc.items(), ("TOPLAM", [sum(v[i] for v in sonuc.values()) for i in range(3)])]:
        print(f"| {tur} | {d / (d + y) if d + y else 0:.0%} | {d / (d + e) if d + e else 0:.0%} | {d} | {y} | {e} |")


def main():
    ayristirici = argparse.ArgumentParser()
    ayristirici.add_argument("--ayrinti", action="store_true")
    s = ayristirici.parse_args()
    print("== Geliştirme seti")
    g = olc(GELISTIRME, s.ayrinti)
    print("== Saklı set")
    k = olc(SAKLI, s.ayrinti)
    tablo("Geliştirme seti", g)
    tablo("Saklı set", k)


if __name__ == "__main__":
    main()
