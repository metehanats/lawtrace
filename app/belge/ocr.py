"""OCR: taranmış PDF sayfalarını görüntüye çevirip Tesseract ile metne dönüştürür.

Okumadan önce sayfaya ön işleme uygulanır (eğiklik ve aydınlatma düzeltme,
yumuşatma; bkz. on_isleme.py).

Tesseract bir Python paketi değildir; bilgisayara ayrıca kurulur ve komut
satırından çağrılır. Türkçe için tur.traineddata dil dosyası gerekir.

Güven skoru, Tesseract'ın kelime başına verdiği güven değerlerinin ortalamasıdır
(0-1). OCR metni hatalı olabilir; bu skor, bulguların avukata gösterilirken
"aslıyla karşılaştırın" uyarısı alıp almayacağına karar vermek için tutulur.
"""

import csv
import io
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pypdfium2 as pdfium
from PIL import Image

from app import ayarlar
from app.belge import on_isleme


class PdfGoruntuleyici:
    """PDF'i bir kez açar, istenen sayfaları tek tek görüntüye çevirir (bellekte tüm sayfalar tutulmaz)."""

    def __init__(self, veri: bytes):
        self._pdf = pdfium.PdfDocument(veri)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self._pdf.close()

    def sayfa(self, sayfa_no: int, dpi: int) -> Image.Image:
        sayfa = self._pdf[sayfa_no - 1]
        try:
            return sayfa.render(scale=dpi / 72, grayscale=True).to_pil()
        finally:
            sayfa.close()


@dataclass
class Kelime:
    metin: str
    guven: float
    sol: int
    sag: int
    ust: int
    alt: int

    @property
    def yukseklik(self) -> int:
        return self.alt - self.ust


# Sütun ayırma kuralları. Tablo ile çok sütunlu metni karıştırmamak için tutucudur:
# yanlışlıkla bölünen bir tablo, satırdaki tarih/tutar ilişkisini koparır.
#
# Bir satırdaki boşluk, kelime yüksekliğinin bu katından genişse sütun boşluğu adayıdır
SUTUN_BOSLUGU_KATSAYISI = 1.5
# Tek sütun boşluğu (iki sütun) varsa ortası metin genişliğinin bu aralığında olmalıdır
SUTUN_BOSLUGU_ARALIGI = (0.3, 0.7)
# Birden çok sütun boşluğu (üç ve daha fazla sütun) varsa her biri bu aralıkta olmalıdır
SUTUN_BOSLUKLARI_ARALIGI = (0.15, 0.85)
# Sütun parçalarında en az bu kadar kelime olmalı (tablo hücreleri çoğunlukla 1-2 kelime).
# Başlık ve son satırlar kısa olabilir; satırların bu oranında her parça bu sayıya ulaşmalıdır.
SUTUN_EN_AZ_KELIME = 3
SUTUN_DOLU_SATIR_ORANI = 0.6
# Çok sütunlu sayılmak için art arda en az bu kadar satır gerekir
SUTUN_EN_AZ_SATIR = 3
# Ortanca boşluk bu katsayıyı aşarsa tablo sayılır. Sağı düzensiz Türkçe metinde ortanca
# ~5,5 x ölçüldü; yalnızca çok geniş boşluklu tabloları dışlar, asıl ayırt edici değildir.
SUTUN_BOSLUGU_EN_FAZLA_KATSAYISI = 8.0
# Düzyazıda cümleler satırdan satıra sürer, satırların bir kısmı küçük harfle başlar.
# Tablo hücreleri her satırda yeni bir kalemdir, çoğunlukla büyük harf ya da rakamla başlar.
# İlk satır dışındaki satırların en az bu oranında bir sütun parçası küçük harfle başlamalı.
SUTUN_KUCUK_HARF_ORANI = 1 / 3
# Tesseract sütun aralığındaki boşluğu bazen tek bir işaret olarak okur ("—", "|").
# Bu işaretler boşluk aranırken yok sayılır; sütun sınırına düşerse metinden de atılır.
_GURULTU_ISARETLERI = set("—–-_|¦·")


def _gurultu(k: Kelime) -> bool:
    return len(k.metin) <= 2 and all(ch in _GURULTU_ISARETLERI for ch in k.metin)


def _tsv_satirlari(tsv: str) -> list[list[list[Kelime]]]:
    """TSV çıktısını paragraflara, paragrafları satırlara, satırları kelimelere ayırır."""
    paragraflar: dict[tuple, dict[tuple, list[Kelime]]] = {}
    for satir in csv.DictReader(io.StringIO(tsv), delimiter="\t", quoting=csv.QUOTE_NONE):
        # level 5 = kelime; -1 güven, kelime olmayan satırları gösterir
        metin = (satir.get("text") or "").replace("\x00", "").strip()
        if satir.get("level") != "5" or not metin:
            continue
        sol, ust = int(satir["left"]), int(satir["top"])
        kelime = Kelime(metin, float(satir["conf"]), sol, sol + int(satir["width"]),
                        ust, ust + int(satir["height"]))
        paragraf = (satir["block_num"], satir["par_num"])
        paragraflar.setdefault(paragraf, {}).setdefault(satir["line_num"], []).append(kelime)
    return [
        [sorted(kelimeler, key=lambda k: k.sol) for kelimeler in satirlar.values()]
        for satirlar in paragraflar.values()
    ]


def _orta_yukseklik(satir: list[Kelime]) -> int:
    return sorted(k.yukseklik for k in satir)[len(satir) // 2]


Bosluk = tuple[int, int]


def _bosluklar(satir: list[Kelime], x0: int, x1: int) -> list[Bosluk]:
    """Satırdaki sütun boşluğu adayları (başlangıç, bitiş), soldan sağa."""
    kelimeler = [k for k in satir if not _gurultu(k)]
    if len(kelimeler) < 2:
        return []
    yukseklik = _orta_yukseklik(kelimeler)
    genislik = max(x1 - x0, 1)
    adaylar = []
    for onceki, sonraki in zip(kelimeler, kelimeler[1:]):
        orta = ((onceki.sag + sonraki.sol) / 2 - x0) / genislik
        if (sonraki.sol - onceki.sag >= SUTUN_BOSLUGU_KATSAYISI * yukseklik
                and SUTUN_BOSLUKLARI_ARALIGI[0] <= orta <= SUTUN_BOSLUKLARI_ARALIGI[1]):
            adaylar.append((onceki.sag, sonraki.sol))
    return adaylar


def _ortak_bosluklar(ortak: list[Bosluk], sonraki: list[Bosluk]) -> list[Bosluk]:
    """İki satırın örtüşen boşlukları (kesişimleri); örtüşmeyenler düşer.

    Geniş bir boşluk (ör. yan yana iki kısa başlık) alttaki birden çok sütun boşluğunu kapsayabilir.
    """
    sonuc = []
    for a in ortak:
        for b in sonraki:
            bas, bit = max(a[0], b[0]), min(a[1], b[1])
            if bas < bit:
                sonuc.append((bas, bit))
    return sonuc


def _parcala(satir: list[Kelime], bosluklar: list[Bosluk]) -> list[list[Kelime]] | None:
    """Kelimeleri sütunlara dağıtır; bir kelime sütun sınırının üstüne düşüyorsa None.

    Sütun boşluğunun içine düşen gürültü işaretleri atılır.
    """
    ortalar = [(a + b) / 2 for a, b in bosluklar]
    parcalar: list[list[Kelime]] = [[] for _ in range(len(ortalar) + 1)]
    for k in satir:
        if _gurultu(k) and any(a <= (k.sol + k.sag) / 2 <= b for a, b in bosluklar):
            continue
        if any(k.sol < o < k.sag for o in ortalar):
            return None
        parcalar[sum(o <= k.sol for o in ortalar)].append(k)
    return parcalar


def _metin_sutunlari(
    blok: list[list[Kelime]], ortak: list[Bosluk], x0: int, genislik: int, dikey_cizgi_var: "CizgiDenetimi | None",
) -> list[list[list[Kelime]]] | None:
    """Blok çok sütunlu düzyazıysa sütunları (her biri satır parçalarının listesi) döndürür; değilse None."""
    if len(blok) < SUTUN_EN_AZ_SATIR:
        return None
    if len(ortak) == 1:
        orta = ((ortak[0][0] + ortak[0][1]) / 2 - x0) / genislik
        if not SUTUN_BOSLUGU_ARALIGI[0] <= orta <= SUTUN_BOSLUGU_ARALIGI[1]:
            return None
    dagilimlar = [_parcala(s, ortak) for s in blok]
    if any(d is None for d in dagilimlar):
        return None
    dolu_satir = sum(all(len(p) >= SUTUN_EN_AZ_KELIME for p in d) for d in dagilimlar)
    if dolu_satir < max(SUTUN_EN_AZ_SATIR, SUTUN_DOLU_SATIR_ORANI * len(blok)):
        return None
    devam_eden = sum(any(p and p[0].metin[0].islower() for p in d) for d in dagilimlar[1:])
    if devam_eden < SUTUN_KUCUK_HARF_ORANI * (len(blok) - 1):
        return None
    # Satırlardaki sütun boşluklarının kelime yüksekliğine oranı
    oranlar = []
    for satir, d in zip(blok, dagilimlar):
        yukseklik = _orta_yukseklik(satir)
        oranlar += [(sag[0].sol - sol[-1].sag) / yukseklik for sol, sag in zip(d, d[1:]) if sol and sag]
    if oranlar and sorted(oranlar)[len(oranlar) // 2] > SUTUN_BOSLUGU_EN_FAZLA_KATSAYISI:
        return None
    y0 = min(k.ust for s in blok for k in s)
    y1 = max(k.alt for s in blok for k in s)
    if dikey_cizgi_var and any(dikey_cizgi_var(a, b, y0, y1) for a, b in ortak):
        return None
    return [[d[n] for d in dagilimlar] for n in range(len(ortak) + 1)]


CizgiDenetimi = Callable[[int, int, int, int], bool]


def _metni_kur(paragraflar: list[list[list[Kelime]]], dikey_cizgi_var: CizgiDenetimi | None = None) -> str:
    """Kelimelerden metni kurar; çok sütunlu bölümlerde sütunları soldan sağa sırayla yazar.

    Tesseract (tüm PSM kiplerinde) yan yana sütunları satır satır birleştiriyordu;
    bu, örneğin davacı iddiası ile davalı savunmasının aynı cümlede okunmasına yol açar.

    dikey_cizgi_var(x0, x1, y0, y1): ön işlemede silinen bir dikey çizginin o bölgede
    olup olmadığını söyler. Sütun boşluğunda dikey çizgi varsa orası tablodur, bölünmez.
    """
    # Sütunlar Tesseract'ın paragraf sınırlarını aşabildiği için satırlar düz bir listede taranır
    satirlar = [(p_no, s) for p_no, p in enumerate(paragraflar) for s in p]
    if not satirlar:
        return ""
    x0 = min(k.sol for _, s in satirlar for k in s)
    x1 = max(k.sag for _, s in satirlar for k in s)

    def yaz(s: list[Kelime]) -> str:
        return " ".join(k.metin for k in s)

    parcalar: list[str] = []
    onceki_paragraf = None
    i = 0
    while i < len(satirlar):
        # Ortak sütun boşluklarını paylaşan en uzun ardışık satır dizisini bul
        ortak = _bosluklar(satirlar[i][1], x0, x1)
        j = i
        while ortak and j + 1 < len(satirlar):
            kesisim = _ortak_bosluklar(ortak, _bosluklar(satirlar[j + 1][1], x0, x1))
            # Yeterince uzun bir blok, boşluklarından birini kaybettiren satırda biter: sütunların
            # kısa son satırları (yalnızca bazı sütunlarda metin) aşağıda ayrıca dağıtılır.
            # Kısa blokta ise ilk satırdaki rastlantısal boşlukların düşmesi beklenir.
            if not kesisim or (len(kesisim) < len(ortak) and j - i + 1 >= SUTUN_EN_AZ_SATIR):
                break
            ortak, j = kesisim, j + 1

        p_no = satirlar[i][0]
        if onceki_paragraf is not None and p_no != onceki_paragraf:
            parcalar.append("")  # paragraf arası boş satır
        blok = [s for _, s in satirlar[i : j + 1]]
        sutunlar = _metin_sutunlari(blok, ortak, x0, max(x1 - x0, 1), dikey_cizgi_var) if ortak else None
        if sutunlar is not None:
            # Sütunların son satırları kısa olabilir (tek kelime) ya da yalnızca bazı sütunlarda
            # kalabilir. Hemen ardından gelen ve sütun sınırlarında kelime bulunmayan satırlar
            # da sütunlara dağıtılır; yoksa öteki sütunlardan sonra yazılırlardı.
            while j + 1 < len(satirlar):
                sonraki = satirlar[j + 1][1]
                yukseklik = _orta_yukseklik(sonraki)
                dagilim = _parcala(sonraki, ortak)
                dolu = [p for p in dagilim or [] if p]
                yakin = sonraki[0].ust - max(k.alt for k in blok[-1]) < 2 * yukseklik
                bolunebilir = dagilim is not None and all(
                    b[0].sol - a[-1].sag >= SUTUN_BOSLUGU_KATSAYISI * yukseklik for a, b in zip(dolu, dolu[1:])
                )
                if not (yakin and bolunebilir):
                    break
                for sutun, parca in zip(sutunlar, dagilim):
                    sutun.append(parca)
                blok.append(sonraki)
                j += 1
            for n, sutun in enumerate(sutunlar):
                if n:
                    parcalar.append("")
                parcalar.extend(yaz(s) for s in sutun if s)
            onceki_paragraf = satirlar[j][0]
            i = j + 1
        else:
            parcalar.append(yaz(satirlar[i][1]))
            onceki_paragraf = p_no
            i += 1
    return "\n".join(parcalar).strip()


def goruntuden_metin(
    goruntu: Image.Image, dikey_cizgi_var: CizgiDenetimi | None = None
) -> tuple[str, float | None]:
    """Görüntüdeki metni ve 0-1 arası güven skorunu döndürür. Metin yoksa skor None olur."""
    with tempfile.TemporaryDirectory(prefix="ocr_") as klasor:
        girdi = Path(klasor) / "sayfa.png"
        cikti = Path(klasor) / "sonuc"
        goruntu.save(girdi)
        subprocess.run(
            [
                ayarlar.tesseract_yolu(), str(girdi), str(cikti),
                "-l", ayarlar.OCR_DILLERI,
                "--tessdata-dir", str(ayarlar.tessdata_dizini()),
                "--psm", ayarlar.OCR_PSM,
                # TSV kelime konumlarını verir; metin bunlardan kurulur. Çıktı türü,
                # tessdata/configs dosyalarına bağlı kalmamak için doğrudan verilir.
                "-c", "tessedit_create_tsv=1",
            ],
            check=True,
            capture_output=True,
            timeout=300,
        )
        paragraflar = _tsv_satirlari(cikti.with_suffix(".tsv").read_text(encoding="utf-8"))

    metin = _metni_kur(paragraflar, dikey_cizgi_var)
    guvenler = [k.guven for p in paragraflar for s in p for k in s if k.guven >= 0]
    if not metin or not guvenler:
        return metin, None
    return metin, round(sum(guvenler) / len(guvenler) / 100, 3)


def sayfayi_oku(goruntu: Image.Image) -> tuple[str, float | None]:
    """Ayarlardaki ön işlemeyi uygulayıp sayfayı okur."""
    islenmis = on_isleme.isle(ayarlar.OCR_ON_ISLEME, goruntu)
    return goruntuden_metin(islenmis.goruntu, islenmis.dikey_cizgi_var)
