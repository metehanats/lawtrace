"""Belge sayfalarından kaynaklı bulgu çıkarma: tarih, tutar, kişi, kurum.

Karma kip (varsayılan): tarih ve tutar kural tabanlı bulunur (kurallar.py), model yalnızca
kişi ve kurum için kullanılır. Model akışı:
1. Sayfalar "[SAYFA n]" işaretleriyle modele verilir; model her bulgu için tür,
   normalize değer, sayfa numarası ve sayfadan BİREBİR kopyalanmış alıntı döndürür.
2. Değer normalize edilir (tarih YYYY-MM-DD / YYYY-MM / YYYY, tutar "123.45 TRY").
3. Kaynak doğrulanır: alıntı belirtilen sayfada bulunmalı ve bulunan değeri
   içermelidir. Doğrulanamayan bulgu ATILIR (projenin ilkesi: kaynaksız bulgu yok).

Bu modül veritabanına dokunmaz; modelden bağımsız birim testlerle sınanır.
"""

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from app.analiz.modeller import DilModeli

TURLER = ("tarih", "tutar", "kisi", "kurum")
# İstem ya da kurallar değişince artırılır; her analiz çalıştırması bu sürümü kaydeder
ISTEM_SURUMU = "karma-1"

SISTEM = """Sen bir hukuk bürosunda dava belgelerini inceleyen dikkatli bir asistansın.
Görevin, verilen belge sayfalarındaki TARİH, TUTAR, KİŞİ ve KURUM bilgilerini çıkarmak.

Kurallar:
- Yalnızca metinde açıkça yazan bilgileri çıkar. Tahmin etme, metinde olmayan hiçbir şey ekleme.
- Her bulgu için "alinti" alanına, bilginin geçtiği yeri sayfadan HARFİ HARFİNE kopyala
  (3-25 kelime; değeri içermeli). Alıntıyı düzeltme, kısaltma, yeniden yazma.
- "sayfa": alıntının geçtiği sayfa numarası ([SAYFA n] işaretindeki n).
- Aynı bilgi aynı sayfada birden çok kez geçiyorsa bir kez yaz; farklı sayfalarda geçiyorsa
  her sayfa için ayrı yaz.
- tarih: "deger" YYYY-MM-DD biçiminde. Yalnızca ay ve yıl belliyse YYYY-MM, yalnızca yıl belliyse YYYY.
- tutar: "deger" "<miktar> <para birimi>" biçiminde, miktar nokta ondalıklı ve 2 haneli,
  para birimi kodu TRY, USD ya da EUR. Örnek: "386.420,50 TL" -> "386420.50 TRY".
- kisi: gerçek kişinin adı soyadı; "Av.", "Dr.", "Stj." gibi unvanları çıkar.
- kurum: şirket, mahkeme, noterlik, banka, kamu kurumu; metindeki tam adıyla.
- Bunlar bulgu DEĞİLDİR: esas/karar/dosya numaraları, T.C. kimlik ve vergi numaraları,
  telefon numaraları, sayfa ve madde numaraları, yüzde oranları, baro sicil numaraları."""

SEMA = {
    "type": "object",
    "properties": {
        "bulgular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tur": {"type": "string", "enum": list(TURLER)},
                    "deger": {"type": "string"},
                    "alinti": {"type": "string"},
                    "sayfa": {"type": "integer"},
                },
                "required": ["tur", "deger", "alinti", "sayfa"],
            },
        }
    },
    "required": ["bulgular"],
}

# Karma kipte model yalnızca kişi ve kurum çıkarır; tarih ve tutar kurallarla bulunur (kurallar.py)
SISTEM_AD = """Sen bir hukuk bürosunda dava belgelerini inceleyen dikkatli bir asistansın.
Görevin, verilen belge sayfalarında adı geçen KİŞİ ve KURUMLARI çıkarmak.

Kurallar:
- Yalnızca metinde açıkça adı geçenleri çıkar. Tahmin etme, metinde olmayan hiçbir ad ekleme.
- Her bulgu için "alinti" alanına, adın geçtiği yeri sayfadan HARFİ HARFİNE kopyala
  (3-25 kelime; adı içermeli). Alıntıyı düzeltme, kısaltma, yeniden yazma.
- "sayfa": alıntının geçtiği sayfa numarası ([SAYFA n] işaretindeki n).
- Aynı ad aynı sayfada birden çok kez geçiyorsa bir kez yaz; farklı sayfalarda geçiyorsa her sayfa için ayrı yaz.
- kisi: gerçek kişinin adı soyadı; "Av.", "Dr.", "Stj." gibi unvanları ve parantez içindeki
  meslek bilgisini çıkar. Bilirkişi, tanık, vekil, yetkili gibi rolleri olan kişiler de kişidir.
- kurum: şirket, mahkeme, noterlik, banka, kamu kurumu; metindeki tam adıyla.
- Bir kişinin soyadı bir şirketin adında geçse bile kişi kişidir, şirket şirkettir."""

SEMA_AD = {
    "type": "object",
    "properties": {
        "bulgular": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "tur": {"type": "string", "enum": ["kisi", "kurum"]},
                    "deger": {"type": "string"},
                    "alinti": {"type": "string"},
                    "sayfa": {"type": "integer"},
                },
                "required": ["tur", "deger", "alinti", "sayfa"],
            },
        }
    },
    "required": ["bulgular"],
}

# Bir model çağrısına verilecek en fazla metin (karakter). Daha uzun belgeler sayfa sınırından bölünür.
# 5000, 4K bağlamlı küçük yerel modelle ölçümde iyi sonuç verdi (docs/devir-notu.md).
PARCA_KARAKTER = 5000


@dataclass
class Bulgu:
    tur: str
    deger: str
    sayfa_no: int
    alinti: str          # sayfadaki özgün yazılışıyla
    baslangic: int       # alıntının sayfa metnindeki karakter konumu
    bitis: int
    yontem: str = "model"    # "kural" (deterministik) ya da "model"
    # Değerin kendisinin sayfadaki konumu (alıntının içinde); bulunamazsa None.
    # Çelişki tespitinde değerin yanındaki etiketi ("dava değeri", "sözleşme tarihi") okumak için.
    deger_baslangic: int | None = None
    deger_bitis: int | None = None


@dataclass
class CikarimSonucu:
    bulgular: list[Bulgu] = field(default_factory=list)
    reddedilen: list[tuple[dict, str]] = field(default_factory=list)   # (ham bulgu, neden)


# --- Normalleştirme -----------------------------------------------------

AYLAR = {
    "ocak": 1, "şubat": 2, "subat": 2, "mart": 3, "nisan": 4, "mayıs": 5, "mayis": 5, "haziran": 6,
    "temmuz": 7, "ağustos": 8, "agustos": 8, "eylül": 9, "eylul": 9, "ekim": 10, "kasım": 11, "kasim": 11,
    "aralık": 12, "aralik": 12,
}


def tr_kucuk(metin: str) -> str:
    return metin.replace("I", "ı").replace("İ", "i").lower()


def tarih_normalle(deger: str) -> str | None:
    d = deger.strip()
    if m := re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", d):
        y, a, g = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{4})-(\d{2})", d):
        y, a = map(int, m.groups())
        return f"{y:04d}-{a:02d}" if 1 <= a <= 12 else None
    elif m := re.fullmatch(r"(\d{4})", d):
        return d
    elif m := re.fullmatch(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", d):
        g, a, y = map(int, m.groups())
    elif m := re.fullmatch(r"(\d{1,2})\s+(\w+)\s+(\d{4})", tr_kucuk(d)):
        g, ay, y = m.groups()
        if ay not in AYLAR:
            return None
        g, a, y = int(g), AYLAR[ay], int(y)
    else:
        return None
    if not (1 <= a <= 12 and 1 <= g <= 31 and 1800 <= y <= 2200):
        return None
    return f"{y:04d}-{a:02d}-{g:02d}"


PARA_BIRIMI = {"try": "TRY", "tl": "TRY", "₺": "TRY", "usd": "USD", "$": "USD", "eur": "EUR", "€": "EUR"}


def _sayi(metin: str) -> float | None:
    s = metin.strip()
    # Türkçe biçim önce denenir: "120.000" 120 değil 120000'dir. Türkçe ondalık en fazla 2 hanedir;
    # virgülden sonra tam 3 hane ("2,000") ABD biçiminde binlik ayraçtır.
    if re.fullmatch(r"\d{1,3}(\.\d{3})+(,\d{1,2})?", s) or re.fullmatch(r"\d+,\d{1,2}", s):   # 386.420,50 · 1500,5
        return float(s.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d+(\.\d+)?", s):                      # 386420.50
        return float(s)
    if re.fullmatch(r"\d{1,3}(,\d{3})+(\.\d+)?", s):          # 2,000.00 (ABD biçimi)
        return float(s.replace(",", ""))
    return None


def tutar_normalle(deger: str) -> str | None:
    d = deger.strip()
    m = re.fullmatch(r"([$€₺])?\s*([\d.,]+)\s*([A-Za-z₺$€]+)?", d)
    if not m:
        return None
    on_ek, sayi, son_ek = m.groups()
    birim = PARA_BIRIMI.get(tr_kucuk(son_ek or on_ek or ""))
    miktar = _sayi(sayi)
    if birim is None or miktar is None:
        return None
    return f"{miktar:.2f} {birim}"


UNVANLAR = re.compile(r"^(av\.|avukat|dr\.|doç\.|prof\.|stj\.|stj\. av\.|sayın)\s+", re.IGNORECASE)

# Adında bunlardan biri geçen bulgu kesinlikle kurumdur (model "kişi" dese de)
KURUM_EKLERI = re.compile(
    r"(^|\s)(a\.ş\.?|ltd\.?|şti\.?|mahkemesi|noterliği|bankası|bakanlığı|müdürlüğü|belediyesi|başkanlığı|"
    r"kurumu|üniversitesi|derneği|vakfı|holding|kooperatifi)(\s|$|[,.])"
)


def ad_normalle(ad: str) -> str:
    a = " ".join(ad.split())
    while (yeni := UNVANLAR.sub("", a)) != a:
        a = yeni
    # Sondaki parantez içi açıklama (ör. "Selma Koç (Mali Müşavir)") addan sayılmaz
    a = re.sub(r"\s*\([^)]*\)\s*$", "", a)
    return a.strip(" ,;:")


def tur_duzelt(tur: str, ad: str) -> str:
    if tur == "kisi" and KURUM_EKLERI.search(tr_kucuk(ad)):
        return "kurum"
    return tur


def ad_anahtari(ad: str) -> str:
    """Karşılaştırma için: Türkçe küçük harf, unvansız, tek boşluk."""
    return tr_kucuk(ad_normalle(ad))


def adlar_esit(a: str, b: str, esik: float = 0.85) -> bool:
    x, y = ad_anahtari(a), ad_anahtari(b)
    return x == y or difflib.SequenceMatcher(None, x, y).ratio() >= esik


# --- Kaynak doğrulama ---------------------------------------------------

_TIRNAKLAR = str.maketrans({"’": "'", "‘": "'", "`": "'", "“": '"', "”": '"', "„": '"', "–": "-", "—": "-"})


def _sadelestir(metin: str) -> tuple[str, list[int]]:
    """Boşlukları teke indirir, tırnakları birleştirir; sade metindeki her karakterin özgün konumunu tutar."""
    sade, konumlar = [], []
    onceki_bosluk = False
    for i, c in enumerate(unicodedata.normalize("NFC", metin)):
        c = c.translate(_TIRNAKLAR)
        if c.isspace():
            if onceki_bosluk:
                continue
            c, onceki_bosluk = " ", True
        else:
            onceki_bosluk = False
        sade.append(c)
        konumlar.append(i)
    return "".join(sade), konumlar


def alinti_bul(sayfa_metni: str, alinti: str) -> tuple[int, int] | None:
    """Alıntının sayfadaki [başlangıç, bitiş) konumu; bulunamazsa None. Büyük/küçük harf duyarlıdır."""
    sade_sayfa, konumlar = _sadelestir(sayfa_metni)
    sade_alinti, _ = _sadelestir(alinti.strip())
    if len(sade_alinti) < 3:
        return None
    i = sade_sayfa.find(sade_alinti)
    if i < 0:
        return None
    return konumlar[i], konumlar[i + len(sade_alinti) - 1] + 1


_AY_ADLARI = "|".join(sorted(AYLAR, key=len, reverse=True))


def alintidaki_tarihler(alinti: str) -> set[str]:
    """Alıntıda yazılı tüm tarihler, normalize edilmiş olarak (tam tarih, ay-yıl ve yıl)."""
    a = tr_kucuk(alinti)
    bulunan: set[str] = set()
    for m in re.finditer(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b", a):
        bulunan.add(tarih_normalle(m.group(0)) or "")
    for m in re.finditer(r"\b(\d{4})-(\d{2})-(\d{2})\b", a):
        bulunan.add(tarih_normalle(m.group(0)) or "")
    for m in re.finditer(rf"\b(\d{{1,2}})\s+({_AY_ADLARI})\s+(\d{{4}})", a):
        bulunan.add(tarih_normalle(m.group(0)) or "")
    # "Mart 2020" (önünde gün yoksa; "12 Mart 2025" yalnızca tam tarih sayılır)
    for m in re.finditer(rf"(?<!\d )\b({_AY_ADLARI})\s+(\d{{4}})\b", a):
        bulunan.add(f"{m.group(2)}-{AYLAR[m.group(1)]:02d}")
    for m in re.finditer(rf"\b(\d{{4}})\s+yılının\s+({_AY_ADLARI})", a):        # "2020 yılının Mart ayında"
        bulunan.add(f"{m.group(1)}-{AYLAR[m.group(2)]:02d}")
    bulunan.update(re.findall(r"\b(1[89]\d{2}|2[01]\d{2})\b", a))               # yalnızca yıl
    bulunan.discard("")
    return bulunan


def alintidaki_miktarlar(alinti: str) -> set[float]:
    miktarlar = set()
    for parca in re.findall(r"\d[\d.,]*\d|\d", alinti):
        if (sayi := _sayi(parca)) is not None:
            miktarlar.add(round(sayi, 2))
    return miktarlar


def deger_alintida_mi(tur: str, deger: str, alinti: str) -> bool:
    """Bulunan değer gerçekten alıntıda yazılı olan değer mi?

    Tarih ve tutar alıntıdan ayrıca ayrıştırılır ve modelin değeriyle birebir karşılaştırılır.
    (İlk ölçümde model "1 Şubat 2019"u 2019-01-01 diye döndürmüş, yalnızca yıla bakan
    eski denetimden geçmişti.)
    """
    a = tr_kucuk(alinti)
    if tur == "tarih":
        return deger in alintidaki_tarihler(alinti)
    if tur == "tutar":
        return round(float(deger.split()[0]), 2) in alintidaki_miktarlar(alinti)
    # kişi / kurum: adın kelimelerinin en az %60'ı alıntıda geçmeli
    kelimeler = [k for k in re.findall(r"\w+", ad_anahtari(deger)) if len(k) > 1]
    if not kelimeler:
        return False
    return sum(k in a for k in kelimeler) / len(kelimeler) >= 0.6


# --- Çıkarım ------------------------------------------------------------

def _parcala(sayfalar: list[str]) -> list[list[tuple[int, str]]]:
    parcalar, simdiki, boy = [], [], 0
    for no, metin in enumerate(sayfalar, start=1):
        if simdiki and boy + len(metin) > PARCA_KARAKTER:
            parcalar.append(simdiki)
            simdiki, boy = [], 0
        simdiki.append((no, metin))
        boy += len(metin)
    if simdiki:
        parcalar.append(simdiki)
    return parcalar


def _istem(parca: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"[SAYFA {no}]\n{metin}" for no, metin in parca)


def ham_bulguyu_dogrula(ham: dict, sayfalar: list[str]) -> Bulgu | str:
    """Doğrulanmış Bulgu ya da reddetme nedeni."""
    tur, deger, alinti, sayfa = ham.get("tur"), str(ham.get("deger", "")), str(ham.get("alinti", "")), ham.get("sayfa")
    if tur not in TURLER:
        return "bilinmeyen tür"
    if not isinstance(sayfa, int) or not 1 <= sayfa <= len(sayfalar):
        return "geçersiz sayfa"
    if tur == "tarih":
        normal = tarih_normalle(deger)
    elif tur == "tutar":
        normal = tutar_normalle(deger)
    else:
        normal = ad_normalle(deger) or None
        tur = tur_duzelt(tur, deger)
    if not normal:
        return "değer biçimi geçersiz"
    konum = alinti_bul(sayfalar[sayfa - 1], alinti)
    if konum is None:
        # Model sayfa numarasını şaşırmış olabilir: alıntı başka bir sayfada birebir geçiyorsa oraya bağlanır
        for no, metin in enumerate(sayfalar, start=1):
            if no != sayfa and (konum := alinti_bul(metin, alinti)):
                sayfa = no
                break
        else:
            return "alıntı belgede yok"
    bas, bit = konum
    ozgun = sayfalar[sayfa - 1][bas:bit]
    if not deger_alintida_mi(tur, normal, ozgun):
        return "değer alıntıyla uyuşmuyor"
    bulgu = Bulgu(tur, normal, sayfa, ozgun, bas, bit)
    if tur in ("kisi", "kurum"):
        # Adın alıntıdaki yeri (büyük/küçük harf duyarsız); unvanlı yazılışı da kapsar
        i = tr_kucuk(ozgun).find(tr_kucuk(normal))
        if i >= 0:
            bulgu.deger_baslangic, bulgu.deger_bitis = bas + i, bas + i + len(normal)
    return bulgu


def _kural_bulgulari(sayfalar: list[str]) -> list[Bulgu]:
    from app.analiz.kurallar import alinti_araligi, tarihleri_bul, tutarlari_bul

    bulgular = []
    for no, metin in enumerate(sayfalar, start=1):
        for k in (*tarihleri_bul(metin), *tutarlari_bul(metin)):
            bas, bit = alinti_araligi(metin, k.baslangic, k.bitis)
            bulgular.append(Bulgu(k.tur, k.deger, no, metin[bas:bit], bas, bit, yontem="kural",
                                  deger_baslangic=k.baslangic, deger_bitis=k.bitis))
    return bulgular


def bulgulari_cikar(model: DilModeli, sayfalar: list[str], karma: bool = True) -> CikarimSonucu:
    """Karma kipte (varsayılan) tarih ve tutar kurallarla, kişi ve kurum modelle bulunur.

    karma=False: dört türün hepsi modelden istenir (karşılaştırma ölçümleri için).
    """
    sonuc = CikarimSonucu()
    gorulen: set[tuple[str, str, int]] = set()

    def ekle(bulgu: Bulgu) -> None:
        anahtar = (bulgu.tur, ad_anahtari(bulgu.deger), bulgu.sayfa_no)
        if anahtar not in gorulen:
            gorulen.add(anahtar)
            sonuc.bulgular.append(bulgu)

    if karma:
        for bulgu in _kural_bulgulari(sayfalar):
            ekle(bulgu)
    sistem, sema = (SISTEM_AD, SEMA_AD) if karma else (SISTEM, SEMA)
    for parca in _parcala(sayfalar):
        yanit = model.json_tamamla(sistem, _istem(parca), sema)
        for ham in yanit.get("bulgular", []):
            if karma and ham.get("tur") in ("tarih", "tutar"):
                continue        # karma kipte bu türler yalnızca kurallardan gelir
            dogrulama = ham_bulguyu_dogrula(ham, sayfalar)
            if isinstance(dogrulama, str):
                sonuc.reddedilen.append((ham, dogrulama))
            else:
                ekle(dogrulama)
    return sonuc
