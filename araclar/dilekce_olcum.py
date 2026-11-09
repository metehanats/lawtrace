"""Dilekçe çeşitliliği setinde iddia bölümleme, delil kalemleri ve etiketleri ölçer (model kullanılmaz).

    python araclar/dilekce_olcum.py            # geliştirme + saklı set
    python araclar/dilekce_olcum.py --ayrinti  # kaçan ve yanlış olanları yazdırır

Eşleşme: beklenen iddia/kalem başı, bulunan parçanın başıyla (Türkçe küçük harf, boşluk sadeleştirilmiş)
karşılaştırılır. Etiket: değer metninin konumunda celiski.etiket_bul sonucu beklenene eşit mi.
"""

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "sentetik_veri"))

from dilekce_cesitlilik import GELISTIRME, SAKLI  # noqa: E402

from app.analiz.celiski import etiket_bul  # noqa: E402
from app.analiz.cikarim import tr_kucuk  # noqa: E402
from app.analiz.iddia import Sayfa, _delil_turu, bolumle  # noqa: E402


def _sade(s: str) -> str:
    return re.sub(r"\s+", " ", tr_kucuk(s)).strip()


def _eslestir(beklenen: list[str], bulunan: list[str]) -> tuple[int, list[str], list[str]]:
    """Sıra gözetmeden: her beklenen, başı uyan ilk kullanılmamış bulunanla eşleşir."""
    kalan = [_sade(b) for b in bulunan]
    dogru, kacan = 0, []
    for b in beklenen:
        hedef = _sade(b)
        i = next((i for i, x in enumerate(kalan) if x.startswith(hedef)), None)
        if i is None:
            kacan.append(b)
        else:
            dogru += 1
            kalan.pop(i)
    return dogru, kacan, kalan


def olc(dilekceler, ayrinti: bool) -> dict:
    s = {"iddia": [0, 0, 0], "delil": [0, 0, 0], "delil_tur": [0, 0], "etiket": [0, 0]}   # doğru, fazla, kaçan
    for d in dilekceler:
        bolum = bolumle([Sayfa(1, d.metin)])
        dogru, kacan, fazla = _eslestir(d.iddialar, [p.metin for p in bolum.iddialar])
        s["iddia"][0] += dogru; s["iddia"][1] += len(fazla); s["iddia"][2] += len(kacan)  # noqa: E702
        if ayrinti and (kacan or fazla):
            print(f"  [{d.ad}] iddia kaçan={kacan} fazla={[f[:40] for f in fazla]}")

        kalemler = [p.metin for p in bolum.deliller]
        dogru, kacan, fazla = _eslestir([k for k, _ in d.deliller], kalemler)
        s["delil"][0] += dogru; s["delil"][1] += len(fazla); s["delil"][2] += len(kacan)  # noqa: E702
        if ayrinti and (kacan or fazla):
            print(f"  [{d.ad}] delil kaçan={kacan} fazla={[f[:40] for f in fazla]}")
        for kalem, tur in d.deliller:
            bulunan = next((k for k in kalemler if _sade(k).startswith(_sade(kalem))), None)
            if bulunan is None:
                continue
            s["delil_tur"][1] += 1
            if _delil_turu(bulunan) == tur:
                s["delil_tur"][0] += 1
            elif ayrinti:
                print(f"  [{d.ad}] delil türü '{kalem}': beklenen {tur}, bulunan {_delil_turu(bulunan)}")

        for deger, tur, etiket in d.etiketler:
            bas = d.metin.index(deger)
            bulunan = etiket_bul(d.metin, bas, bas + len(deger), tur)
            s["etiket"][1] += 1
            if bulunan == etiket:
                s["etiket"][0] += 1
            elif ayrinti:
                print(f"  [{d.ad}] etiket '{deger}': beklenen {etiket}, bulunan {bulunan}")
    return s


def _yaz(ad: str, s: dict) -> None:
    def oran(d, f, k):
        kesinlik = d / (d + f) if d + f else 1.0
        duyarlilik = d / (d + k) if d + k else 1.0
        return f"kesinlik %{kesinlik * 100:.0f}, duyarlılık %{duyarlilik * 100:.0f} ({d} doğru, {f} fazla, {k} kaçan)"
    print(f"{ad}")
    print(f"  İddia bölümleme : {oran(*s['iddia'])}")
    print(f"  Delil kalemleri : {oran(*s['delil'])}")
    print(f"  Delil türü      : %{s['delil_tur'][0] / max(1, s['delil_tur'][1]) * 100:.0f} "
          f"({s['delil_tur'][0]}/{s['delil_tur'][1]}, yalnızca bulunan kalemlerde)")
    print(f"  Etiket          : %{s['etiket'][0] / max(1, s['etiket'][1]) * 100:.0f} ({s['etiket'][0]}/{s['etiket'][1]})")


def main() -> None:
    ayr = argparse.ArgumentParser()
    ayr.add_argument("--ayrinti", action="store_true")
    a = ayr.parse_args()
    for ad, kume in (("GELİŞTİRME", GELISTIRME), ("SAKLI", SAKLI)):
        if a.ayrinti:
            print(f"--- {ad} ayrıntı ---")
        _yaz(ad, olc(kume, a.ayrinti))


if __name__ == "__main__":
    main()
