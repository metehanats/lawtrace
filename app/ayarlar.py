"""Uygulama ayarları. Değerler ortam değişkenlerinden okunur; parola veya adres koda yazılmaz."""

import os
from pathlib import Path

# Tek bir belge için üst sınır (bayt)
MAKS_BELGE_BOYUTU = int(os.environ.get("MAKS_BELGE_BOYUTU", 50 * 1024 * 1024))

# İşçi, bekleyen görev yokken bu kadar saniye bekleyip yeniden bakar
ISCI_BEKLEME_SANIYE = float(os.environ.get("ISCI_BEKLEME_SANIYE", 5))

# Geçici hatada bir görev en fazla bu kadar kez denenir (ilk deneme dahil)
MAKS_DENEME = int(os.environ.get("MAKS_DENEME", 3))
# Yeniden denemeden önce beklenen süre; her başarısız denemede iki katına çıkar (60 sn, 120 sn, ...)
YENIDEN_DENEME_TABAN_SANIYE = float(os.environ.get("YENIDEN_DENEME_TABAN_SANIYE", 60))


def _mantiksal(ad: str, varsayilan: bool) -> bool:
    deger = os.environ.get(ad)
    return varsayilan if deger is None else deger.strip().lower() in ("1", "true", "evet", "on")


# Kimlik doğrulama
OTURUM_COOKIE_ADI = os.environ.get("OTURUM_COOKIE_ADI", "oturum")
# Çerez yalnızca HTTPS üzerinden gönderilsin. Tarayıcılar http://localhost'u güvenli sayar,
# bu yüzden yerel geliştirmede de açık kalabilir.
OTURUM_COOKIE_GUVENLI = _mantiksal("OTURUM_COOKIE_GUVENLI", True)
OTURUM_SURESI_SAAT = float(os.environ.get("OTURUM_SURESI_SAAT", 12))     # en uzun oturum süresi
OTURUM_BOSTA_DAKIKA = float(os.environ.get("OTURUM_BOSTA_DAKIKA", 60))  # işlem yapılmazsa kapanır
GIRIS_KILIT_ESIGI = int(os.environ.get("GIRIS_KILIT_ESIGI", 5))         # art arda hatalı giriş
GIRIS_KILIT_DAKIKA = float(os.environ.get("GIRIS_KILIT_DAKIKA", 15))
PAROLA_EN_AZ_UZUNLUK = int(os.environ.get("PAROLA_EN_AZ_UZUNLUK", 12))


def veritabani_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL ortam değişkeni tanımlı değil.")
    return url


# OCR ayarları. Varsayılanlar araclar/ocr_kalite.py ölçümüyle seçildi (bkz. docs/ocr-kalite-raporu.md).
# Dil: "tur+eng", yalnız "tur"a göre "%" işaretini doğru okuyor ve Türkçe harflerde kayıp yok.
OCR_DILLERI = os.environ.get("OCR_DILLERI", "tur+eng")
OCR_DPI = int(os.environ.get("OCR_DPI", 300))
# Tesseract sayfa bölütleme kipi: 3 = otomatik, 4 = tek sütun, 6 = tek metin bloğu.
# 4, 3'teki satır sırası karışmasını gideriyor. Yan yana iki metin sütununu hiçbir kip
# ayıramıyor; bunu ocr.py kelime konumlarından kendisi yapıyor.
OCR_PSM = os.environ.get("OCR_PSM", "4")
# Güven skoru bu değerin altındaki (ya da skoru olmayan) OCR sayfaları "aslıyla karşılaştırın"
# uyarısıyla gösterilir. Sentetik ölçümde doğru sayfalar >= 0,95, hatalı fakslar <= 0,91 çıktı.
OCR_UYARI_ESIGI = float(os.environ.get("OCR_UYARI_ESIGI", 0.93))
# app/belge/on_isleme.py içindeki YONTEMLER anahtarlarından biri
OCR_ON_ISLEME = os.environ.get("OCR_ON_ISLEME", "egiklik_arka_plan_cizgi_yumusat")


def tesseract_yolu() -> str:
    deger = os.environ.get("TESSERACT_YOLU")
    if deger:
        return deger
    varsayilan = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    return str(varsayilan) if varsayilan.exists() else "tesseract"


def veri_koku() -> Path:
    """Uygulama verilerinin (veritabanı, belgeler, OCR dil dosyaları, yedekler) kök klasörü.

    Varsayılan %USERPROFILE%\\AvukatDosyaTakipVeri. AppData BİLEREK kullanılmaz: paketli (MSIX)
    uygulamalar içinden çalışan süreçlerin AppData'ya yazdıkları, paketin sanal klasörüne yönlendirilir.
    Böyle yazılan veriyi Görev Zamanlayıcı ya da kullanıcının kendi terminali göremez; paket
    kaldırılınca da veri silinir. db/db-baslat.ps1 aynı kökü kullanır.
    """
    deger = os.environ.get("AVUKAT_VERI_KOKU")
    return Path(deger) if deger else Path.home() / "AvukatDosyaTakipVeri"


def tessdata_dizini() -> Path:
    """Tesseract dil dosyalarının (tur.traineddata vb.) bulunduğu klasör."""
    deger = os.environ.get("TESSDATA_DIZINI")
    if deger:
        return Path(deger)
    return veri_koku() / "tessdata"


def yedek_klasoru() -> Path:
    """Yedeklerin yazıldığı klasör. Bugün aynı bilgisayarda; harici diske almak için YEDEK_KLASORU."""
    deger = os.environ.get("YEDEK_KLASORU")
    if deger:
        return Path(deger)
    return veri_koku() / "yedekler"


def pg_araci(ad: str) -> str:
    """pg_dump / pg_restore yolu; PG_BIN ile değiştirilebilir."""
    dizin = Path(os.environ.get("PG_BIN", r"C:\Program Files\PostgreSQL\18\bin"))
    yol = dizin / f"{ad}.exe"
    return str(yol) if yol.exists() else ad


def depolama_koku() -> Path:
    """Yüklenen belgelerin yerel depolama klasörü.

    Varsayılan konum proje klasörünün dışındadır; böylece yüklenen belgeler
    proje dosyalarına karışmaz.
    """
    deger = os.environ.get("DEPOLAMA_KOKU")
    if deger:
        return Path(deger)
    return veri_koku() / "depolama"
