"""Belgeler arası çelişki (uyuşmazlık) tespiti.

Yorum yapmaz; metindeki ETİKETE bakar:
- Tarih ve tutar: değerin yanında "dava değeri", "sözleşme tarihi", "işe başlama" gibi bir etiket
  varsa bulgu o etiketle saklanır. Tek değeri olması beklenen bir etiket dosyada farklı
  değerlerle geçiyorsa çelişkidir. Birden çok değeri olabilen etiketler ("fatura", "ödeme")
  bilerek dışarıda bırakılır; yoksa her fatura bir çelişki sayılırdı.
- Kişi ve kurum: aynı ad belgelerde farklı yazılmışsa ("İsmail Güneş" / "İsmail Gunes")
  düşük önemli çelişkidir. Yalnızca noktalama farkı (OCR) sayılmaz; düşük güvenli OCR
  sayfasından gelen yazım farkı da sayılmaz (gürültü olur).
- Avukatın reddettiği bulgu çelişki hesabına girmez.

Bu bir yardımcıdır: bulduğu çelişki "kesin" değildir, avukatın incelemesi için işaretlenir.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass
from itertools import combinations

from app.analiz.cikarim import ad_anahtari, tr_kucuk

# (etiket adı, metinde aranan kalıplar). Kalıplar Türkçe küçük harfle, kelime başından eşleşir.
# Ek alınca değişen son harfler kalıba konmaz: "alacak" → "alacağın" (k→ğ) olduğu için "asıl alaca".
TEK_DEGERLI_ETIKETLER = {
    "tutar": [
        ("dava değeri", ["dava değeri", "dava değerimiz", "harca esas"]),
        ("asıl alacak", ["asıl alaca"]),
        ("talep edilen toplam", ["toplam alaca", "toplam talep", "toplam tutar", "toplamı", "alacak tutar",
                                 "talep miktar"]),
        ("cezai şart", ["cezai şart"]),
        ("kıdem tazminatı", ["kıdem tazminatı"]),
        ("ihbar tazminatı", ["ihbar tazminatı"]),
        ("son ücret", ["son brüt ücret", "son net ücret", "son aylık", "aylık brüt ücret", "son ücret"]),
        ("depozito", ["depozito", "kapora"]),
        ("vekalet ücreti", ["vekalet ücreti"]),
    ],
    "tarih": [
        # "imzala" gövdesi: imzalamış, imzalanmış, imzaladı, imzalandı
        # "akded" gövdesi: akdedilmiş, akdedildiği
        ("sözleşme tarihi", ["sözleşme tarihi", "sözleşme imzala", "sözleşmesi imzala", "sözleşmenin imzala",
                             "sözleşme ile", "sözleşme akded", "sözleşmesi akded", "sözleşmenin akded"]),
        ("kira başlangıç tarihi", ["kira başlangıç", "başlangıç tarihli kira"]),
        ("olay tarihi", ["olay tarihi", "kaza", "çarpma"]),
        ("ihtarname tarihi", ["ihtarname", "ihtar"]),
        ("tebliğ tarihi", ["tebliğ"]),
        ("işe başlama tarihi", ["işe başla", "çalışmaya başla", "işe giriş"]),
        ("fesih tarihi", ["fesih", "feshedil", "işten çıkar", "iş akdi sona"]),
        ("teslim tarihi", ["teslim tarihi", "teslim edil"]),
        ("dava tarihi", ["dava tarihi", "dava açıl"]),
        ("karar tarihi", ["karar tarihi", "tarihli karar"]),
        ("yatış tarihi", ["yatış"]),
        ("taburcu tarihi", ["taburcu"]),
    ],
}

# Değerden en fazla bu kadar karakter uzaktaki etiket sayılır; aynı satır ve aynı cümle içinde
# ("… tarihinde işveren tarafından haklı neden olmaksızın feshedilmiştir" fiili cümle sonundadır)
ETIKET_MESAFESI = 100
# Aynı cümlede ikisi birden geçerse daha belirgin olan seçilir: "ihtarname … tebliğ edilmiştir"
# cümlesindeki tarih ihtarnamenin tebliğ tarihidir
ONCELIK = {"ihtarname tarihi": "tebliğ tarihi"}
# İki parçalı etiket: değer araya girer ("Sözleşme 03.11.2024 tarihinde imzalanmıştır")
# (etiket, değerden önce gelen sözcük, değerden sonra gelen fiil gövdeleri)
IKI_PARCALI = [("tarih", "sözleşme tarihi", "sözleşme", ("imzala", "akded"))]
_CUMLE_SINIRI = re.compile(r"[.!?;](?=\s)")


@dataclass
class CeliskiBulgusu:
    """Çelişki hesabının ihtiyaç duyduğu bulgu bilgisi (veritabanından bağımsız)."""
    id: object
    tur: str
    deger: str
    ozet: str
    etiket: str | None
    belge_id: object
    belge_adi: str
    sayfa_no: int
    dogrulama_durumu: str
    ocr_supheli: bool = False


@dataclass
class Celiski:
    tur: str                 # uyusmazlik.tur: tarih | tutar | kisi_kurum
    bulgu_1: CeliskiBulgusu
    bulgu_2: CeliskiBulgusu
    aciklama: str
    ciddiyet: str            # dusuk | orta | yuksek


def _kaliplar(tur: str):
    for etiket, kaliplar in TEK_DEGERLI_ETIKETLER.get(tur, []):
        for k in kaliplar:
            yield etiket, re.compile(r"(?<![a-zçğıöşü])" + re.escape(k))


def etiket_bul(sayfa_metni: str, deger_bas: int, deger_bit: int, tur: str) -> str | None:
    """Değerin aynı satırda, aynı cümlede ve yakınında geçen, tek değerli etiketi; en yakın olanı."""
    satir_bas = sayfa_metni.rfind("\n", 0, deger_bas) + 1
    satir_bit = sayfa_metni.find("\n", deger_bit)
    satir_bit = len(sayfa_metni) if satir_bit < 0 else satir_bit
    pencere_bas = max(satir_bas, deger_bas - ETIKET_MESAFESI)
    pencere_bit = min(satir_bit, deger_bit + ETIKET_MESAFESI)
    # Cümle sınırını aşma (tarih içindeki noktalar "03.11.2024" sınır sayılmaz: ardında boşluk yok)
    for m in _CUMLE_SINIRI.finditer(sayfa_metni, pencere_bas, deger_bas):
        pencere_bas = m.end()
    if (m := _CUMLE_SINIRI.search(sayfa_metni, deger_bit, pencere_bit)) is not None:
        pencere_bit = m.start()
    pencere = tr_kucuk(sayfa_metni[pencere_bas:pencere_bit])
    d_bas, d_bit = deger_bas - pencere_bas, deger_bit - pencere_bas
    en_iyi: tuple[int, str] | None = None
    gorulen: set[str] = set()
    for etiket, kalip in _kaliplar(tur):
        for m in kalip.finditer(pencere):
            # Etiket ile değer arasındaki boşluk; önde olan etiket hafifçe tercih edilir
            if m.end() <= d_bas:
                uzaklik = d_bas - m.end()
            elif m.start() >= d_bit:
                uzaklik = m.start() - d_bit + 5
            else:
                continue
            gorulen.add(etiket)
            if en_iyi is None or uzaklik < en_iyi[0]:
                en_iyi = (uzaklik, etiket)
    for t, etiket, once, fiiller in IKI_PARCALI:
        sonra = re.search(r"(?<![a-zçğıöşü])(?:" + "|".join(fiiller) + ")", pencere[d_bit:])
        if t == tur and sonra and re.search(r"(?<![a-zçğıöşü])" + once, pencere[:d_bas]):
            uzaklik = sonra.start() + 5        # sonraki etiket gibi sayılır
            gorulen.add(etiket)
            if en_iyi is None or uzaklik < en_iyi[0]:
                en_iyi = (uzaklik, etiket)
    if en_iyi is None:
        return None
    oncelikli = ONCELIK.get(en_iyi[1])
    return oncelikli if oncelikli in gorulen else en_iyi[1]


def yazim_anahtari(ad: str) -> str:
    """Noktalama ve boşluk farkını yok sayan ad anahtarı."""
    return re.sub(r"[^\wçğıöşü]+", " ", ad_anahtari(ad)).strip()


def _ascii(metin: str) -> str:
    duz = metin.replace("ı", "i")
    return "".join(c for c in unicodedata.normalize("NFKD", duz) if not unicodedata.combining(c))


def _temsilci(bulgular: list[CeliskiBulgusu]) -> CeliskiBulgusu:
    # Onaylanmış bulgu önce, sonra belge adı ve sayfa sırası (sonuç kararlı olsun)
    return sorted(bulgular, key=lambda b: (b.dogrulama_durumu != "onaylandi", b.belge_adi, b.sayfa_no))[0]


def _kaynak(b: CeliskiBulgusu) -> str:
    return f"{b.belge_adi} s. {b.sayfa_no}"


def celiskileri_bul(bulgular: list[CeliskiBulgusu]) -> list[Celiski]:
    gecerli = [b for b in bulgular if b.dogrulama_durumu != "reddedildi"]
    celiskiler: list[Celiski] = []

    # Tarih ve tutar: aynı tek değerli etiket, farklı değerler
    etiketli: dict[tuple[str, str], dict[str, list[CeliskiBulgusu]]] = {}
    for b in gecerli:
        if b.tur in ("tarih", "tutar") and b.etiket:
            etiketli.setdefault((b.tur, b.etiket), {}).setdefault(b.deger, []).append(b)
    for (tur, etiket), degerler in sorted(etiketli.items()):
        if len(degerler) < 2:
            continue
        for d1, d2 in combinations(sorted(degerler), 2):
            b1, b2 = _temsilci(degerler[d1]), _temsilci(degerler[d2])
            celiskiler.append(Celiski(
                tur, b1, b2,
                f"\"{etiket}\" belgelerde farklı: {b1.ozet} ({_kaynak(b1)}) ve {b2.ozet} ({_kaynak(b2)}).",
                "yuksek" if tur == "tutar" else "orta",
            ))

    # Kişi ve kurum: aynı adın farklı yazılışları
    adlar: dict[tuple[str, str], list[CeliskiBulgusu]] = {}
    for b in gecerli:
        if b.tur in ("kisi", "kurum") and not b.ocr_supheli:
            adlar.setdefault((b.tur, yazim_anahtari(b.deger)), []).append(b)
    for (tur1, a1), (tur2, a2) in combinations(sorted(adlar), 2):
        if tur1 != tur2 or a1 == a2:
            continue
        ayni_kisi = _ascii(a1) == _ascii(a2) or difflib.SequenceMatcher(None, a1, a2).ratio() >= 0.9
        if not ayni_kisi:
            continue
        b1, b2 = _temsilci(adlar[(tur1, a1)]), _temsilci(adlar[(tur2, a2)])
        celiskiler.append(Celiski(
            "kisi_kurum", b1, b2,
            f"Aynı {'kişi' if tur1 == 'kisi' else 'kurum'} farklı yazılmış olabilir: "
            f"\"{b1.deger}\" ({_kaynak(b1)}) ve \"{b2.deger}\" ({_kaynak(b2)}).",
            "dusuk",
        ))
    return celiskiler
