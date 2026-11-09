"""İddia–belge eşlemesini ölçer: mevcut kurallar, yerel model ve ikisinin birleşimi.

    python araclar/iddia_eslesme_olcum.py                    # geliştirme seti, üç yöntem
    python araclar/iddia_eslesme_olcum.py --set sakli        # saklı set (yöntem ayarlandıktan SONRA)
    python araclar/iddia_eslesme_olcum.py --ayrinti          # yanlış ve kaçan bağları yazdırır
    python araclar/iddia_eslesme_olcum.py --yontem kural     # modelsiz (Ollama gerekmez)

Veri: tests/sentetik_veri/iddia_eslesme.py (uydurma). Ölçüt: bağ başına kesinlik/duyarlılık.
"kabul" kümesindeki belgeye kurulan bağ yanlış sayılmaz ama doğru da sayılmaz.

Model yöntemi bir ÖN DENEMEDİR (ürüne eklenmedi): model her bağ için belgeden kelimesi kelimesine
bir alıntı vermek zorundadır. Alıntı belgede bulunamazsa bağ atılır (kaynaksız bulgu kaydedilmez
ilkesi). "doğrulanmamış" satırı, bu denetim olmasaydı sonucun ne olacağını gösterir.
"""

import argparse
import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "sentetik_veri"))

from iddia_eslesme import GELISTIRME, SAKLI, Dosya  # noqa: E402

from app.analiz.cikarim import alinti_bul  # noqa: E402
from app.analiz.iddia import DosyaBelgesi, Sayfa, _iddia_anar, ek_no, kokler  # noqa: E402
from app.analiz.kurallar import tarihleri_bul, tutarlari_bul  # noqa: E402
from app.analiz.modeller import ModelHatasi, OllamaModeli  # noqa: E402

BELGE_KIRP = 1500   # belge başına modele giden en fazla karakter

SISTEM = """Sen bir Türk avukatına yardım eden dikkatli bir asistansın.
Sana dilekçeden bir iddia ve dava dosyasındaki belgeler verilecek. Görevin, iddiadaki olguyu
doğrudan destekleyen ya da çürüten bilgiyi içeren belgeleri bulmaktır.

Kurallar:
- Bir belgeyi yalnızca metninde iddiadaki olguyu (sözleşme, teslim, ödeme, uyarı, fesih, hasar,
  tarih, tutar, beyan vb.) gösteren somut bir ifade varsa seç. Konu benzerliği yetmez.
- Her seçim için o ifadeyi belgeden KELİMESİ KELİMESİNE kopyala. Alıntı belgede aynen geçmelidir;
  değiştirme, özetleme, birleştirme.
- İddiadaki olguyu gösteren hiçbir belge yoksa boş liste döndür. Emin değilsen seçme."""

SEMA = {
    "type": "object",
    "properties": {
        "baglar": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"belge": {"type": "integer"}, "alinti": {"type": "string"}},
                "required": ["belge", "alinti"],
            },
        }
    },
    "required": ["baglar"],
}


DOGRULA_SISTEM = """Sen bir Türk avukatına yardım eden titiz bir denetçisin.
Sana dilekçeden bir iddia ve bir belgeden bir alıntı verilecek. Soru: alıntı, iddiada ileri sürülen
olgunun KENDİSİNİ (ya da tam tersini) gösteriyor mu?

- Evet: alıntı iddiadaki olayı, işlemi, tarihi, tutarı ya da beyanı doğrudan anlatıyor.
- Hayır: alıntı yalnızca aynı taraflardan, aynı olaydan ya da aynı konudan söz ediyor ama iddiadaki
  olguyu göstermiyor; ya da iddianın yalnızca bir arka planıdır.
Yalnızca kesinse "evet" de."""

DOGRULA_SEMA = {
    "type": "object",
    "properties": {"gerekce": {"type": "string"}, "gosteriyor": {"type": "boolean"}},
    "required": ["gerekce", "gosteriyor"],
}


def _degerler(metin: str) -> set[tuple[str, str]]:
    return {(b.tur, b.deger) for b in tarihleri_bul(metin) + tutarlari_bul(metin)}


def kural_baglari(dosya: Dosya, iddia: str) -> set[str]:
    """app/analiz/iddia.py'deki kurallar: Ek-N atfı, anılan belge adı, aynı tarih/tutar."""
    sonuc = set()
    ik = kokler(iddia)
    deger = _degerler(iddia)
    n = ek_no(iddia)
    for b in dosya.belgeler:
        db = DosyaBelgesi(b.ad, b.ad, [Sayfa(1, b.metin)])
        if (n and db.ek_no() == n) or _iddia_anar(ik, db) or (deger & _degerler(b.metin)):
            sonuc.add(b.ad)
    return sonuc


def model_baglari(model: OllamaModeli, dosya: Dosya, iddia: str, dogrula: bool = False
                  ) -> tuple[set[str], set[str], set[str]]:
    """(alıntısı belgede bulunan bağlar, modelin önerdiği tüm bağlar, ikinci denetimden geçenler)."""
    belgeler = "\n\n".join(f"[{i}] {b.ad}\n{b.metin[:BELGE_KIRP]}" for i, b in enumerate(dosya.belgeler, 1))
    yanit = model.json_tamamla(SISTEM, f"İDDİA:\n{iddia}\n\nBELGELER:\n{belgeler}", SEMA)
    hepsi, dogrulanan, denetlenen = set(), set(), set()
    for bag in yanit.get("baglar", []):
        no = bag.get("belge")
        if not isinstance(no, int) or not 1 <= no <= len(dosya.belgeler):
            continue
        belge = dosya.belgeler[no - 1]
        hepsi.add(belge.ad)
        alinti = (bag.get("alinti") or "").strip()
        if len(alinti) >= 10 and alinti_bul(belge.metin, alinti):
            dogrulanan.add(belge.ad)
            if dogrula:
                karar = model.json_tamamla(DOGRULA_SISTEM, f"İDDİA:\n{iddia}\n\nALINTI ({belge.ad}):\n{alinti}",
                                           DOGRULA_SEMA)
                if karar.get("gosteriyor") is True:
                    denetlenen.add(belge.ad)
    return dogrulanan, hepsi, denetlenen


class Sayac:
    def __init__(self):
        self.dogru = self.yanlis = self.kacan = 0
        self.bos_iddia_yanlis = 0

    def ekle(self, bulunan: set[str], beklenen: set[str], kabul: set[str]) -> tuple[set[str], set[str]]:
        yanlis = bulunan - beklenen - kabul
        kacan = beklenen - bulunan
        self.dogru += len(bulunan & beklenen)
        self.yanlis += len(yanlis)
        self.kacan += len(kacan)
        if not beklenen and yanlis:
            self.bos_iddia_yanlis += 1
        return yanlis, kacan

    def satir(self, ad: str) -> str:
        kesinlik = self.dogru / (self.dogru + self.yanlis) if self.dogru + self.yanlis else math.nan
        duyarlilik = self.dogru / (self.dogru + self.kacan) if self.dogru + self.kacan else math.nan
        f1 = 2 * kesinlik * duyarlilik / (kesinlik + duyarlilik) if kesinlik + duyarlilik else 0
        return (f"| {ad} | {self.dogru} | {self.yanlis} | {self.kacan} | {kesinlik:.0%} | {duyarlilik:.0%} "
                f"| {f1:.0%} | {self.bos_iddia_yanlis} |")


def main() -> None:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--set", choices=["gelistirme", "sakli"], default="gelistirme")
    ayristirici.add_argument("--yontem", choices=["hepsi", "kural"], default="hepsi")
    ayristirici.add_argument("--model", default="qwen3.5:4b")
    ayristirici.add_argument("--ayrinti", action="store_true")
    ayristirici.add_argument("--dogrula", action="store_true", help="Her bağı ikinci bir model çağrısıyla denetle")
    secenek = ayristirici.parse_args()
    dosyalar = GELISTIRME if secenek.set == "gelistirme" else SAKLI
    model = OllamaModeli(secenek.model, baglam=8192) if secenek.yontem == "hepsi" else None

    sayaclar = {ad: Sayac() for ad in ("kural", "model", "model (doğrulanmamış)", "kural + model",
                                       "model + denetim", "kural + model + denetim")}
    sure, cagri, hata = 0.0, 0, 0
    bos_sayisi = sum(not i.beklenen for d in dosyalar for i in d.iddialar)
    for dosya in dosyalar:
        for iddia in dosya.iddialar:
            sonuclar = {"kural": kural_baglari(dosya, iddia.metin)}
            if model:
                t = time.perf_counter()
                try:
                    dogrulanan, hepsi, denetlenen = model_baglari(model, dosya, iddia.metin, secenek.dogrula)
                except ModelHatasi as h:
                    print(f"  model hatası: {h}")
                    dogrulanan, hepsi, denetlenen, hata = set(), set(), set(), hata + 1
                sure += time.perf_counter() - t
                cagri += 1
                sonuclar |= {"model": dogrulanan, "model (doğrulanmamış)": hepsi,
                             "kural + model": sonuclar["kural"] | dogrulanan}
                if secenek.dogrula:
                    sonuclar |= {"model + denetim": denetlenen,
                                 "kural + model + denetim": sonuclar["kural"] | denetlenen}
            for ad, bulunan in sonuclar.items():
                yanlis, kacan = sayaclar[ad].ekle(bulunan, iddia.beklenen, iddia.kabul)
                if secenek.ayrinti and ad in ("model", "model + denetim") and (yanlis or kacan):
                    print(f"  [{ad}] {iddia.metin[:70]}…  yanlış={sorted(yanlis)} kaçan={sorted(kacan)}")

    print(f"\nSet: {secenek.set} ({sum(len(d.iddialar) for d in dosyalar)} iddia, {bos_sayisi} tanesi hiçbir "
          f"belgeyle ilgisiz; {sum(len(i.beklenen) for d in dosyalar for i in d.iddialar)} beklenen bağ)")
    if model:
        print(f"Model: {secenek.model}, iddia başına ortalama {sure / max(cagri, 1):.1f} sn, hata: {hata}")
    print("\n| yöntem | doğru | yanlış | kaçan | kesinlik | duyarlılık | F1 | ilgisiz iddiaya bağ |")
    print("|---|---|---|---|---|---|---|---|")
    for ad, s in sayaclar.items():
        if s.dogru + s.yanlis + s.kacan:
            print(s.satir(ad))


if __name__ == "__main__":
    main()
