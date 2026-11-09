"""OCR öncesi görüntü ön işleme yöntemleri.

Her yöntem, gri tonlamalı sayfa görüntüsüne sırayla uygulanan adımlardan oluşur
(bkz. YONTEMLER); görüntünün boyutu değişmez. Hangi yöntemin kullanılacağı
araclar/ocr_kalite.py ve araclar/ocr_duzen.py ölçümlerine göre seçilir.
"""

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageFilter


def otsu_esigi(a: np.ndarray) -> int:
    if a.min() == a.max():
        # Tek renkli (boş) sayfa: eşik yok, her şey kâğıt sayılır
        return int(a.min())
    hist = np.bincount(a.ravel(), minlength=256).astype(np.float64)
    toplam = hist.sum()
    agirlik = np.cumsum(hist)
    ortalama = np.cumsum(hist * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        arasi = (ortalama[-1] * agirlik - ortalama * toplam) ** 2 / (agirlik * (toplam - agirlik))
    return int(np.nanargmax(arasi))


def egiklik_acisi(goruntu: Image.Image, aralik: float = 6.0, adim: float = 0.2) -> float:
    """Satırların yataydan sapma açısını yatay izdüşüm yöntemiyle bulur (derece)."""
    kucuk = goruntu.resize((goruntu.width // 4, goruntu.height // 4), Image.BILINEAR)
    a = np.asarray(kucuk)
    maske = a < otsu_esigi(a)
    if not maske.any():
        return 0.0
    murekkep = Image.fromarray((maske * 255).astype(np.uint8))
    en_iyi_aci, en_iyi_skor = 0.0, -1.0
    for aci in np.arange(-aralik, aralik + adim / 2, adim):
        profil = np.asarray(murekkep.rotate(aci, resample=Image.NEAREST, fillcolor=0), dtype=np.float64).sum(axis=1)
        # Satırlar yatay olduğunda satır ve satır arası farkı en keskin olur
        skor = float(np.sum(np.diff(profil) ** 2))
        if skor > en_iyi_skor:
            en_iyi_aci, en_iyi_skor = float(aci), skor
    return en_iyi_aci


def egiklik_duzelt(goruntu: Image.Image) -> Image.Image:
    aci = egiklik_acisi(goruntu)
    if abs(aci) < 0.3:
        return goruntu
    return goruntu.rotate(aci, resample=Image.BICUBIC, fillcolor=255)


def arka_plan_duzelt(goruntu: Image.Image) -> Image.Image:
    """Düzensiz aydınlatmayı (gölge, sararmış kâğıt) giderir; kâğıdı beyaza çeker."""
    kucuk = goruntu.resize((goruntu.width // 8, goruntu.height // 8), Image.BILINEAR)
    # En büyük değer süzgeci mürekkebi siler, geriye kâğıdın aydınlığı kalır
    arka = kucuk.filter(ImageFilter.MaxFilter(7)).filter(ImageFilter.GaussianBlur(6))
    arka = np.asarray(arka.resize(goruntu.size, Image.BILINEAR), dtype=np.float32)
    a = np.asarray(goruntu, dtype=np.float32)
    duz = np.clip(a / np.maximum(arka, 1) * 255, 0, 255)
    return Image.fromarray(duz.astype(np.uint8))


def _uzun_kosular(maske: np.ndarray, uzunluk: int) -> np.ndarray:
    """Her satırda en az `uzunluk` piksel boyunca kesintisiz süren True koşularını işaretler."""
    toplam = np.cumsum(np.pad(maske, ((0, 0), (1, 0))).astype(np.int32), axis=1)
    pencere = toplam[:, uzunluk:] - toplam[:, :-uzunluk]          # her başlangıç için pencere toplamı
    dolu = (pencere == uzunluk).astype(np.int32)
    # Dolu bir pencerenin kapsadığı her piksel işaretlenir
    kapsama = np.cumsum(np.pad(dolu, ((0, 0), (uzunluk, 0))), axis=1)
    kapsama = kapsama[:, uzunluk:] - kapsama[:, :-uzunluk]
    sonuc = np.zeros_like(maske)
    sonuc[:, : kapsama.shape[1]] = kapsama > 0
    return sonuc


def cizgi_sil(goruntu: Image.Image, uzunluk: int = 150) -> tuple[Image.Image, np.ndarray | None]:
    """Tablo ve form çizgilerini (uzun yatay/dikey çizgiler) siler.

    Çizgiler Tesseract'ın satır bölütlemesini bozuyor; çizgili tablolarda satırların
    çoğu hiç okunmuyordu. 300 dpi'da 150 piksel (~1,3 cm) harf vuruşlarından çok uzundur.

    Silinen dikey çizgilerin maskesini de döndürür: dikey çizgi, orada bir tablo
    olduğunu gösterir ve sütun ayırmanın tabloyu bölmesini önlemek için kullanılır.
    """
    a = np.asarray(goruntu)
    murekkep = a < otsu_esigi(a)
    if not murekkep.any():
        return goruntu, None
    yatay = _uzun_kosular(murekkep, uzunluk)
    dikey = _uzun_kosular(murekkep.T, uzunluk).T
    if not (yatay.any() or dikey.any()):
        return goruntu, None
    # Kenar yumuşatmasından kalan gri izleri de almak için çizgi bir piksel kalınlaştırılır
    cizgi = np.asarray(Image.fromarray((yatay | dikey).astype(np.uint8) * 255).filter(ImageFilter.MaxFilter(3))) > 0
    temiz = a.copy()
    temiz[cizgi] = 255
    return Image.fromarray(temiz), (dikey if dikey.any() else None)


def yumusat(goruntu: Image.Image) -> Image.Image:
    """Faks ve düşük çözünürlükteki basamaklı kenarları yumuşatır."""
    return goruntu.filter(ImageFilter.GaussianBlur(1.2))


def ikilestir(goruntu: Image.Image) -> Image.Image:
    a = np.asarray(goruntu)
    return Image.fromarray(((a > otsu_esigi(a)) * 255).astype(np.uint8))


@dataclass
class OnIslenmis:
    goruntu: Image.Image
    # Silinen dikey çizgilerin maskesi (görüntüyle aynı boyutta); çizgi yoksa None
    dikey_cizgi: np.ndarray | None = None

    def __post_init__(self):
        self._integral = None
        if self.dikey_cizgi is not None:
            self._integral = np.pad(self.dikey_cizgi.astype(np.int32).cumsum(0).cumsum(1), ((1, 0), (1, 0)))

    def dikey_cizgi_var(self, x0: int, x1: int, y0: int, y1: int) -> bool:
        """Verilen dikdörtgende silinmiş bir dikey çizgi parçası var mı?"""
        if self._integral is None:
            return False
        h, w = self.dikey_cizgi.shape
        x0, x1 = max(0, x0), min(w, x1)
        y0, y1 = max(0, y0), min(h, y1)
        if x0 >= x1 or y0 >= y1:
            return False
        s = self._integral
        return bool(s[y1, x1] - s[y0, x1] - s[y1, x0] + s[y0, x0] > 0)


ADIMLAR = {
    "egiklik": egiklik_duzelt,
    "arka_plan": arka_plan_duzelt,
    "yumusat": yumusat,
    "ikili": ikilestir,
}

# Her yöntem sırayla uygulanacak adımların listesidir ("cizgi" = cizgi_sil)
YONTEMLER = {
    "yok": [],
    "egiklik": ["egiklik"],
    "arka_plan": ["arka_plan"],
    "egiklik_arka_plan": ["egiklik", "arka_plan"],
    "egiklik_arka_plan_ikili": ["egiklik", "arka_plan", "ikili"],
    "egiklik_arka_plan_yumusat": ["egiklik", "arka_plan", "yumusat"],
    "egiklik_arka_plan_cizgi_yumusat": ["egiklik", "arka_plan", "cizgi", "yumusat"],
}


def isle(yontem: str, goruntu: Image.Image) -> OnIslenmis:
    dikey = None
    for adim in YONTEMLER[yontem]:
        if adim == "cizgi":
            goruntu, dikey = cizgi_sil(goruntu)
        else:
            goruntu = ADIMLAR[adim](goruntu)
    return OnIslenmis(goruntu, dikey)
