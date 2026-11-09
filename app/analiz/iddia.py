"""İddia–delil haritası: dilekçedeki iddiaları dosyadaki belgelerle ilişkilendirir.

Model kullanmaz; dilekçenin HMK 119'daki olağan yapısına ve metindeki izlere dayanır:
- Bölümler başlıktan tanınır: AÇIKLAMALAR / SAVUNMALARIMIZ (iddialar), DELİLLER, ve
  bölümü bitiren HUKUKİ SEBEPLER, SONUÇ VE İSTEM, EKLER vb. Başlıksız dilekçe haritalanmaz.
- İddia bir paragraftır: numaralı yazılmışsa numaradan numaraya, değilse cümle sonu ile biten
  satıra kadar. Sayfa sonunda kesilir (alıntı tek sayfada kalsın, kaynakta işaretlenebilsin).
- Bağlar, en güçlüden zayıfa:
  ek atfı      iddiada "Ek-3" geçer, dosyada adı/başlığı "EK-3" olan belge var;
  anılan belge iddia, belgenin adındaki kelimelerin en az yarısını içerir ("ihtarname gönderilmiş");
  aynı değer   iddiadaki tarih/tutar başka bir (dilekçe olmayan) belgede de geçer;
  çelişki      iddiadaki tarih/tutar açık bir çelişkinin tarafıdır.
- Delil listesindeki her kalem dosyadaki belgelerle eşlenir; belge olması beklenip dosyada
  bulunamayan kalem "eksik" işaretlenir. Tanık, keşif, yemin gibi belge dışı deliller ve
  başka yerden getirtilecek kayıtlar eksik sayılmaz.

Bu bir yardımcıdır: bağ "kanıtlar" anlamına gelmez, avukatın bakacağı yeri gösterir.
Kelime eşleşmesi kök yaklaşımıyla (ilk 5 harf) yapılır; anlamsal ilişki aranmaz.
"""

import math
import re
from dataclasses import dataclass, field

from app.analiz.cikarim import tr_kucuk

KOK_UZUNLUGU = 5
# Belge adlarında ve delil kalemlerinde ayırt edici olmayan kelimeler (kök olarak karşılaştırılır)
DURAK = {
    "ve", "ile", "veya", "bir", "olan", "ait", "ilgili", "göre", "dair", "tarihli", "tarihinde", "sayılı",
    "nolu", "örneği", "sureti", "aslı", "fotokopisi", "tarama", "taranmış", "telefon", "fotoğrafı", "faks",
    "kopya", "belge", "belgeler", "ekler", "ekleri", "davalı", "davacı", "müvekkil", "gönderilen",
    "düzenlenen", "dilekçe", "sentetik", "mahkemesi", "esas", "taraf", "dosyaya", "sunulan", "pdf", "docx",
}

# (bölüm türü, başlıklar). Uzun başlık önce denenir ("sonuç ve istem" "sonuç"tan önce).
BASLIKLAR = {
    "iddia": ["açıklamalar", "açıklama", "maddi olaylar", "maddi vakıalar", "vakıalar", "olayların özeti",
              "olaylar", "izahat", "savunmalarımız", "cevaplarımız", "itirazlarımız", "savunma"],
    "delil": ["hukuki deliller", "deliller ve ekler", "delil listesi", "delillerimiz", "deliller"],
    "diger": ["hukuki sebepler", "hukuki nedenler", "hukuki dayanaklar", "hukuki sebep", "sonuç ve istem",
              "sonuç ve talep", "netice-i talep", "netice ve talep", "netice ve istem", "talep sonucu", "sonuç", "ekler", "ek listesi",
              "konu", "davacı vekili", "davalı vekili", "davacı", "davalı", "vekili"],
}
# Başlık önekleri: Romen ya da Arap rakamı ("I-", "2."; Türkçe küçük harfte "I" → "ı") ve
# cevap dilekçelerindeki "esasa/usule ilişkin" ("ESASA İLİŞKİN CEVAPLARIMIZ").
# Başlığın sonunda iyelik eki olabilir: "AÇIKLAMALARIMIZ", "OLAYLARIMIZ".
_BASLIK_RE = re.compile(
    r"^[ \t]*(?:(?:[ıivx]+|\d{1,2})[.)-][ \t]*)?(?:(?:esasa|usule)[ \t]+ilişkin[ \t]+)?("
    + "|".join(re.escape(b) for b in sorted((b for bs in BASLIKLAR.values() for b in bs), key=len, reverse=True))
    + r")(?:ımız|imiz|umuz|ümüz)?[ \t]*(?::|$)",
    re.MULTILINE,
)
_BASLIK_TURU = {b: tur for tur, bs in BASLIKLAR.items() for b in bs}
# Madde numarası: "1.", "1-", "1)", "1 -" ya da harfle "a)"; "4.2. maddesi" madde sayılmaz
_NUMARA_RE = re.compile(r"^[ \t]*(?:\d{1,2}[ \t]*[.)-][ \t]+(?=\D)|[a-zA-ZçğıöşüÇĞİÖŞÜ]\)[ \t]+)")
_CUMLE_SONU = (".", "!", "?", ":", ";")
_EK_RE = re.compile(r"\bek[ \t]*[-:.]?[ \t]*(\d{1,3})\b")
# Satır ortasında numara yalnızca "2-" ya da "2)" biçiminde sayılır: "İstanbul 3. İcra" bölünmesin.
# Satır başındaki madde işareti ("- Kaza tespit tutanağı", "• Faturalar") kaleme dahil edilmez.
_DELIL_AYRAC = re.compile(
    r"[ \t]*(?:[,;\n]|\bve\b|(?<![\d.])\d{1,2}[ \t]*[)-](?=[ \t])|^\d{1,2}\.(?=[ \t])|^[-•*](?=[ \t]))[ \t]*")
# Belge olmayan deliller ve başka yerden getirtilecek kayıtlar (kök olarak; "kaydı": kayıt yumuşaması)
BELGE_DISI = {"tanık", "keşif", "yemin", "istic", "bilir", "uzman", "türlü", "sair", "delil", "beyan"}
DIS_KAYNAK = {"dosya", "kayıt", "kaydı", "celp", "müzek", "sicil", "sgk", "tapu"}
EN_KISA_IDDIA = 15


def kokler(metin: str) -> set[str]:
    kelimeler = re.findall(r"[a-zçğıöşüâîû]+", tr_kucuk(re.sub(r"\([^)]*\)", " ", metin)))
    return {k[:KOK_UZUNLUGU] for k in kelimeler if len(k) >= 3 and k not in DURAK} - _DURAK_KOKLERI


_DURAK_KOKLERI = {k[:KOK_UZUNLUGU] for k in DURAK if len(k) >= 3}


def ek_no(metin: str) -> str | None:
    m = _EK_RE.search(tr_kucuk(metin))
    return m.group(1) if m else None


@dataclass
class Sayfa:
    sayfa_no: int
    metin: str


@dataclass
class Parca:
    """Dilekçeden bir iddia ya da delil kalemi; sayfa metnindeki konumuyla."""
    sayfa_no: int
    bas: int
    bit: int
    metin: str


@dataclass
class Dilekce:
    iddialar: list[Parca]
    deliller: list[Parca]


def _satirlar(sayfalar: list[Sayfa]):
    for s in sayfalar:
        konum = 0
        for satir in s.metin.split("\n"):
            yield s, konum, konum + len(satir)
            konum += len(satir) + 1


def _kirp(sayfa: Sayfa, bas: int, bit: int) -> Parca | None:
    parca = sayfa.metin[bas:bit]
    bas += len(parca) - len(parca.lstrip())
    bit -= len(parca) - len(parca.rstrip(" \t\n."))
    return Parca(sayfa.sayfa_no, bas, bit, sayfa.metin[bas:bit]) if bit > bas else None


def bolumle(sayfalar: list[Sayfa]) -> Dilekce:
    # Her satırı bölüm türüyle etiketle; başlık satırında içerik başlıktan sonra başlar
    satirlar: list[tuple[Sayfa, int, int, str | None]] = []
    bolum: str | None = None
    for sayfa, bas, bit in _satirlar(sayfalar):
        if m := _BASLIK_RE.match(tr_kucuk(sayfa.metin[bas:bit])):
            bolum = _BASLIK_TURU[m.group(1)]
            bas += m.end()
        satirlar.append((sayfa, bas, bit, bolum))

    iddia_satirlari = [s for s in satirlar if s[3] == "iddia"]
    numarali = any(_NUMARA_RE.match(sy.metin[b:e]) for sy, b, e, _ in iddia_satirlari)
    iddialar: list[Parca] = []
    acik: tuple[Sayfa, int, int] | None = None
    onceki: tuple[Sayfa, int, int, str | None] | None = None

    def kapat():
        nonlocal acik
        if acik and (p := _kirp(*acik)) and len(p.metin) >= EN_KISA_IDDIA \
                and not re.match(r"sayfa\s*\d", tr_kucuk(p.metin)):
            iddialar.append(p)
        acik = None

    for satir in satirlar:
        sayfa, bas, bit, tur = satir
        metin = sayfa.metin[bas:bit].strip()
        bitisik = onceki is not None and onceki[3] == "iddia" and onceki[0] is sayfa
        if tur != "iddia" or not metin or not bitisik:
            kapat()
        elif numarali and _NUMARA_RE.match(sayfa.metin[bas:bit]):
            kapat()
        elif not numarali and onceki[0].metin[onceki[1]:onceki[2]].rstrip().endswith(_CUMLE_SONU):
            kapat()
        if tur == "iddia" and metin:
            if numarali and (m := _NUMARA_RE.match(sayfa.metin[bas:bit])):
                bas += m.end()
            acik = (sayfa, acik[1], bit) if acik else (sayfa, bas, bit)
        onceki = satir
    kapat()

    deliller: list[Parca] = []
    for sayfa, bas, bit, tur in satirlar:
        if tur != "delil":
            continue
        satir = tr_kucuk(sayfa.metin[bas:bit])
        konum = 0
        # Türkçe sayımda "ve" yalnızca son kalemi bağlar ("A, B ve C"); ortadaki "ihtarname ve tebliğ
        # şerhi" tek kalemdir. Bu yüzden "ve" yalnızca satırdaki son virgülden sonra ayırır.
        son_virgul = max(satir.rfind(","), satir.rfind(";"))
        ayraclar = [a for a in _DELIL_AYRAC.finditer(satir) if a.group().strip() != "ve" or a.start() > son_virgul]
        for ayrac in [*ayraclar, None]:
            son = ayrac.start() if ayrac else len(satir)
            # Boş ya da tek harfli parçalar kalem değildir. Kök kümesi değil harf aranır: belge adı
            # eşlemesinde ayırt edici sayılmayan bir kelime ("fotoğraflar") da tek başına delil kalemidir.
            if (p := _kirp(sayfa, bas + konum, bas + son)) and re.search(r"[a-zçğıöşüâîû]{3}", tr_kucuk(p.metin)):
                deliller.append(p)
            konum = ayrac.end() if ayrac else konum
    return Dilekce(iddialar, deliller)


# --- Dosya düzeyinde harita -------------------------------------------------

@dataclass
class DosyaBelgesi:
    id: object
    ad: str
    sayfalar: list[Sayfa]       # metni okunamayan / onaysız özel nitelikli belgede boş

    @property
    def baslik(self) -> str:
        ilk = self.sayfalar[0].metin if self.sayfalar else ""
        return next((s.strip() for s in ilk.split("\n") if s.strip()), "")

    def anahtarlar(self) -> list[set[str]]:
        """Belgeyi tanıyan kelime kümeleri: dosya adı (uzantısız) ve ilk satır başlığı."""
        ad = re.sub(r"\.[a-z0-9]{2,5}$", "", self.ad, flags=re.I)
        return [k for k in (kokler(_EK_RE.sub(" ", tr_kucuk(ad))), kokler(_EK_RE.sub(" ", tr_kucuk(self.baslik))))
                if k]

    def ek_no(self) -> str | None:
        return next((n for n in (_bas_ek(self.ad), _bas_ek(self.baslik)) if n), None)

    @property
    def dilekce_adli(self) -> bool:
        return "dilekçe" in tr_kucuk(f"{self.ad} {self.baslik}")


def _bas_ek(metin: str) -> str | None:
    m = re.match(r"[ \t]*ek[ \t]*[-:.]?[ \t]*(\d{1,3})\b", tr_kucuk(metin))
    return m.group(1) if m else None


@dataclass
class DegerBulgusu:
    id: object
    belge_id: object
    sayfa_no: int
    tur: str
    deger: str
    ozet: str
    bas: int                    # değerin sayfa metnindeki konumu
    bit: int
    alinti: str
    alinti_bas: int | None
    alinti_bit: int | None
    dogrulama_durumu: str


@dataclass
class Bag:
    tur: str                    # ek_atfi | anilan_belge | ayni_deger | celiski
    belge_id: object
    belge_adi: str
    aciklama: str
    sayfa_no: int | None = None
    bas: int | None = None
    bit: int | None = None
    alinti: str | None = None


@dataclass
class Iddia:
    no: int
    sayfa_no: int
    bas: int
    bit: int
    metin: str
    baglar: list[Bag]

    @property
    def dayanaksiz(self) -> bool:
        return not any(b.tur != "celiski" for b in self.baglar)


@dataclass
class Delil:
    metin: str
    sayfa_no: int
    bas: int
    bit: int
    tur: str                    # dosyada | eksik | belge_disi | dis_kaynak
    belgeler: list[dict] = field(default_factory=list)


@dataclass
class DilekceHaritasi:
    belge_id: object
    belge_adi: str
    iddialar: list[Iddia]
    deliller: list[Delil]


def _delil_eslesir(kalem: str, belge: DosyaBelgesi) -> bool:
    if (n := ek_no(kalem)) and n == belge.ek_no():
        return True
    k = kokler(_EK_RE.sub(" ", tr_kucuk(kalem)))
    # Kalemin kelimelerinin en az yarısı belgeyi tanıtmalı ("Sözleşme" → "Mal satış sözleşmesi")
    return bool(k) and any(len(k & a) >= max(1, math.ceil(len(k) / 2)) for a in belge.anahtarlar())


def _iddia_anar(iddia: set[str], belge: DosyaBelgesi) -> bool:
    # Belge adının en az yarısı iddiada geçmeli ("ihtarname gönderilmiş" → "İhtarname")
    return any(len(iddia & a) >= max(1, math.ceil(len(a) / 2)) for a in belge.anahtarlar())


def _delil_turu(kalem: str) -> str:
    k = {w[:KOK_UZUNLUGU] for w in re.findall(r"[a-zçğıöşü]+", tr_kucuk(kalem))}
    if k & BELGE_DISI:
        return "belge_disi"
    if k & DIS_KAYNAK:
        return "dis_kaynak"
    return "eksik"


def harita_olustur(
    belgeler: list[DosyaBelgesi], bulgular: list[DegerBulgusu], celiskiler: dict | None = None,
) -> list[DilekceHaritasi]:
    """`celiskiler`: bulgu id → [(açıklama, karşı bulgu id)] (yalnızca açık tarih/tutar çelişkileri)."""
    celiskiler = celiskiler or {}
    bolumler = {b.id: bolumle(b.sayfalar) for b in belgeler}
    dilekceler = [b for b in belgeler if bolumler[b.id].iddialar or bolumler[b.id].deliller]
    # Başlıksız dilekçe haritalanmaz ama delil de sayılmaz (taraf beyanıdır)
    dilekce_idleri = {b.id for b in belgeler if b in dilekceler or b.dilekce_adli}
    kanitlar = [b for b in belgeler if b.id not in dilekce_idleri]
    adlar = {b.id: b.ad for b in belgeler}
    gecerli = [b for b in bulgular if b.dogrulama_durumu != "reddedildi"]
    bulgu_idleri = {b.id: b for b in bulgular}

    haritalar = []
    for dilekce in dilekceler:
        bolum = bolumler[dilekce.id]
        iddialar = []
        for no, p in enumerate(bolum.iddialar, 1):
            baglar: list[Bag] = []
            if (n := ek_no(p.metin)):
                baglar += [Bag("ek_atfi", b.id, b.ad, f"İddiada Ek-{n} anılıyor.") for b in kanitlar if b.ek_no() == n]
            ik = kokler(p.metin)
            baglar += [Bag("anilan_belge", b.id, b.ad, "Belgenin adı iddiada geçiyor.")
                       for b in kanitlar if _iddia_anar(ik, b) and all(x.belge_id != b.id for x in baglar)]
            icindeki = [b for b in gecerli if b.belge_id == dilekce.id and b.sayfa_no == p.sayfa_no
                        and p.bas <= b.bas and b.bit <= p.bit]
            for d in icindeki:
                gorulen = set()
                for b in sorted(gecerli, key=lambda x: (adlar[x.belge_id], x.sayfa_no)):
                    if (b.tur, b.deger) == (d.tur, d.deger) and b.belge_id not in dilekce_idleri \
                            and b.belge_id not in gorulen:
                        gorulen.add(b.belge_id)
                        baglar.append(Bag("ayni_deger", b.belge_id, adlar[b.belge_id],
                                          f"{d.ozet} bu belgede de geçiyor.", b.sayfa_no, b.alinti_bas,
                                          b.alinti_bit, b.alinti))
                for aciklama, karsi_id in celiskiler.get(d.id, []):
                    if (k := bulgu_idleri.get(karsi_id)):
                        baglar.append(Bag("celiski", k.belge_id, adlar.get(k.belge_id, ""), aciklama, k.sayfa_no,
                                          k.alinti_bas, k.alinti_bit, k.alinti))
            iddialar.append(Iddia(no, p.sayfa_no, p.bas, p.bit, p.metin, baglar))

        deliller = []
        for p in bolum.deliller:
            eslesen = [{"belge_id": b.id, "belge_adi": b.ad} for b in kanitlar if _delil_eslesir(p.metin, b)]
            deliller.append(Delil(p.metin, p.sayfa_no, p.bas, p.bit,
                                  "dosyada" if eslesen else _delil_turu(p.metin), eslesen))
        haritalar.append(DilekceHaritasi(dilekce.id, dilekce.ad, iddialar, deliller))
    return haritalar
