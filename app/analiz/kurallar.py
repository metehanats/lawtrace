"""Tarih ve tutarların kural tabanlı (deterministik) çıkarımı.

Tarih ve tutar belirli kalıplarla yazılır; düzenli ifadelerle bulunmaları modelden hem
daha güvenilir hem çok daha hızlıdır. Her bulgunun kaynağı, kalıbın sayfada eşleştiği
yerdir; yani kaynak doğrulaması kendiliğinden sağlanır.

Bilerek BULUNMAYANLAR: esas/karar numaraları ("2025/1487"), kimlik ve telefon
numaraları, yüzde oranları, madde numaraları, yalnız başına yıllar ("2021") ve
para birimi yazılmamış sayılar. Para birimi olmayan sayı tutar sayılmaz.

Alıntı olarak, bulgunun geçtiği satır (çok uzunsa çevresindeki bölüm) verilir.
"""

import re
from dataclasses import dataclass

from app.analiz.cikarim import AYLAR, PARA_BIRIMI, _sayi, tarih_normalle, tr_kucuk


@dataclass
class KuralBulgusu:
    tur: str
    deger: str
    baslangic: int      # bulgunun (kalıbın) sayfadaki konumu
    bitis: int


_AY = "|".join(sorted(AYLAR, key=len, reverse=True))
# Sayının bir parçası olmamak için: önünde harf, rakam, nokta ya da eğik çizgi olmasın;
# arkasında harf, rakam, eğik çizgi ya da ondalık devamı olmasın. Tire serbest: "01.01.2024-31.12.2024".
_SINIR_ONCE = r"(?<![\w./])"
_SINIR_SONRA = r"(?![\w/]|[.,]\d)"

_TARIH_KALIPLARI = [
    # 03.11.2024 · 3/11/2024 · 03-11-2024
    (re.compile(_SINIR_ONCE + r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})" + _SINIR_SONRA), "gun"),
    # 2.11.24 (iki haneli yıl; yalnızca noktalı yazımda)
    (re.compile(_SINIR_ONCE + r"(\d{1,2})\.(\d{1,2})\.(\d{2})" + _SINIR_SONRA), "gun_kisa"),
    # 2024-11-03
    (re.compile(_SINIR_ONCE + r"(\d{4})-(\d{2})-(\d{2})" + _SINIR_SONRA), "iso"),
    # 12 Mart 2025
    (re.compile(_SINIR_ONCE + rf"(\d{{1,2}})\s+({_AY})\s+(\d{{4}})\b"), "yazili"),
    # 2020 yılının Mart ayında · 2020 yılı Mart ayı
    (re.compile(_SINIR_ONCE + rf"(\d{{4}})\s+yılı(?:nın)?\s+({_AY})\b"), "yil_ay"),
    # Mart 2020 (önünde gün yoksa)
    (re.compile(rf"(?<!\d )\b({_AY})\s+(\d{{4}})\b"), "ay_yil"),
    # 2021 yılında · 2019 yılından · 2021 yılı (olayın yılı)
    (re.compile(_SINIR_ONCE + r"(1[89]\d\d|20\d\d)\s+yılı(?:nda|ndan|na|nı|nın)?\b"), "yil"),
]

_SAYI = r"\d{1,3}(?:\.\d{3})+(?:,\d{1,2})?|\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:[.,]\d{1,2})?"
_HARF = r"a-zçğıöşü"
# Para birimi (sonda). "lira", "dolar", "avro" Türkçe ekleri doğrudan alır ("liraya", "dolarlık").
_BIRIM_SONRA = (
    rf"(?:TL|TRY|₺|USD|EUR)(?![{_HARF}])"
    rf"|türk\s+lira[{_HARF}]*|abd\s+dolar[{_HARF}]*|lira[{_HARF}]*|dolar[{_HARF}]*|(?:euro|avro)[{_HARF}]*"
)
# "5.000.-TL", "7.500-TL", "5.000,-TL" icra yazımları
_AYRAC = r"(?:\.-|,-|-)?"
# "1,5 milyon", "18 bin", "2 milyon 400 bin"
_BUYUK = (
    rf"(?P<s1>{_SAYI})\s+(?P<c1>milyar|milyon|bin)"
    rf"(?:\s+(?P<s2>\d{{1,3}}(?:,\d{{1,2}})?)\s+(?P<c2>milyon|bin))?"
)
_TUTAR_SONRA = re.compile(
    _SINIR_ONCE + rf"(?:{_BUYUK}|(?P<sade>{_SAYI}))\s*{_AYRAC}\s*(?P<birim>{_BIRIM_SONRA})", re.IGNORECASE
)
# Para birimi önde: "$2,000", "₺5.000", "TL 2.500", "USD 3.000"
_TUTAR_ONCE = re.compile(rf"(?:(?P<sembol>[$€₺])|(?<![\w])(?P<kod>TL|TRY|USD|EUR)\s+)(?P<sayi>{_SAYI})" + _SINIR_SONRA)

_CARPAN = {"bin": 1_000, "milyon": 1_000_000, "milyar": 1_000_000_000}

# Yazıyla tutar: "beş bin Türk lirası", "onbin lira", "yüz elli bin TL"
_BIRLER = {"bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_ONLAR = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80,
          "doksan": 90}
_KELIME_SAYI = "|".join(sorted([*_BIRLER, *_ONLAR, "yüz", *_CARPAN], key=len, reverse=True))
_YAZIYLA = re.compile(
    rf"(?<![{_HARF}\w])((?:{_KELIME_SAYI})(?:\s*(?:{_KELIME_SAYI}))*)\s*(?P<birim>{_BIRIM_SONRA})", re.IGNORECASE
)


def _birim(metin: str) -> str | None:
    m = " ".join(tr_kucuk(metin).split())
    if m in PARA_BIRIMI:
        return PARA_BIRIMI[m]
    for onek, kod in (("türk lira", "TRY"), ("lira", "TRY"), ("abd dolar", "USD"), ("dolar", "USD"),
                      ("euro", "EUR"), ("avro", "EUR")):
        if m.startswith(onek):
            return kod
    return None


def _yaziyla_sayi(metin: str) -> int | None:
    toplam = grup = 0
    for kelime in re.findall(_KELIME_SAYI, metin):
        if kelime in _BIRLER:
            grup += _BIRLER[kelime]
        elif kelime in _ONLAR:
            grup += _ONLAR[kelime]
        elif kelime == "yüz":
            grup = (grup or 1) * 100
        else:
            toplam += (grup or 1) * _CARPAN[kelime]
            grup = 0
    toplam += grup
    return toplam or None


def tarihleri_bul(metin: str) -> list[KuralBulgusu]:
    kucuk = tr_kucuk(metin)
    if len(kucuk) != len(metin):        # konumlar kaymasın diye (beklenmez, ama güvenlik için)
        kucuk = metin.lower()
    bulunan: list[KuralBulgusu] = []
    dolu: list[tuple[int, int]] = []
    for kalip, tur in _TARIH_KALIPLARI:
        for m in kalip.finditer(kucuk):
            bas, bit = m.span()
            if any(b < bit and bas < s for b, s in dolu):     # daha ayrıntılı kalıp zaten eşleşti
                continue
            if tur in ("gun", "iso", "yazili"):
                deger = tarih_normalle(metin[bas:bit])
            elif tur == "gun_kisa":
                g, a, y = (int(x) for x in m.groups())
                deger = tarih_normalle(f"{g}.{a}.{(2000 if y < 70 else 1900) + y}")
            elif tur == "yil_ay":
                deger = f"{m.group(1)}-{AYLAR[m.group(2)]:02d}"
            elif tur == "ay_yil":
                deger = f"{m.group(2)}-{AYLAR[m.group(1)]:02d}"
            else:
                deger = m.group(1)
            if deger:
                bulunan.append(KuralBulgusu("tarih", deger, bas, bit))
                dolu.append((bas, bit))
    return sorted(bulunan, key=lambda b: b.baslangic)


def _buyuk_miktar(m: re.Match) -> float | None:
    s1 = _sayi(m.group("s1"))
    if s1 is None:
        return None
    c1 = _CARPAN[m.group("c1").lower()]
    miktar = s1 * c1
    if m.group("s2"):
        c2 = _CARPAN[m.group("c2").lower()]
        s2 = _sayi(m.group("s2"))
        if s2 is None or c2 >= c1:
            return None
        miktar += s2 * c2
    return miktar


def tutarlari_bul(metin: str) -> list[KuralBulgusu]:
    bulunan: list[KuralBulgusu] = []

    def ekle(miktar: float | None, birim: str | None, bas: int, bit: int) -> None:
        if miktar is not None and birim and not any(b.baslangic < bit and bas < b.bitis for b in bulunan):
            bulunan.append(KuralBulgusu("tutar", f"{miktar:.2f} {birim}", bas, bit))

    for m in _TUTAR_SONRA.finditer(metin):
        miktar = _buyuk_miktar(m) if m.group("s1") else _sayi(m.group("sade"))
        ekle(miktar, _birim(m.group("birim")), *m.span())
    for m in _TUTAR_ONCE.finditer(metin):
        ekle(_sayi(m.group("sayi")), _birim(m.group("sembol") or m.group("kod")), *m.span())
    kucuk = tr_kucuk(metin)
    if len(kucuk) == len(metin):
        for m in _YAZIYLA.finditer(kucuk):
            ekle(_yaziyla_sayi(m.group(1)), _birim(m.group("birim")), *m.span())
    return sorted(bulunan, key=lambda b: b.baslangic)


def alinti_araligi(metin: str, bas: int, bit: int, en_fazla: int = 240) -> tuple[int, int]:
    """Bulgunun geçtiği satır; satır çok uzunsa bulgunun çevresindeki kelime sınırlı bölüm."""
    satir_bas = metin.rfind("\n", 0, bas) + 1
    satir_bit = metin.find("\n", bit)
    satir_bit = len(metin) if satir_bit < 0 else satir_bit
    if satir_bit - satir_bas <= en_fazla:
        a, b = satir_bas, satir_bit
    else:
        pay = max(0, (en_fazla - (bit - bas)) // 2)
        a, b = max(satir_bas, bas - pay), min(satir_bit, bit + pay)
        # kelime ortasında kesilmesin
        while a > satir_bas and not metin[a - 1].isspace():
            a -= 1
        while b < satir_bit and not metin[b].isspace():
            b += 1
    while a < b and metin[a].isspace():
        a += 1
    while b > a and metin[b - 1].isspace():
        b -= 1
    return a, b
