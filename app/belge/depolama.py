"""Belge dosyalarının saklanması.

Depolama anahtarı büro, dava ve belge kimliklerinden oluşur; orijinal dosya adı
anahtara konmaz, çünkü dosya adları kişisel bilgi içerebilir.

Dosyalar diskte şifreli durur: SifreliDepolama, altındaki depolamaya (bugün YerelDepolama,
ileride S3 uyumlu bir depolama) yalnızca şifreli bayt verir. Uygulama her zaman
varsayilan_depolama() üzerinden çalışır; YerelDepolama tek başına kullanılmaz.
"""

import os
from pathlib import Path
from typing import Protocol
from uuid import UUID

from app import ayarlar, kripto


def anahtar_olustur(buro_id: UUID, dava_id: UUID, belge_id: UUID) -> str:
    return f"{buro_id}/{dava_id}/{belge_id}"


class Depolama(Protocol):
    def kaydet(self, anahtar: str, veri: bytes) -> None: ...
    def oku(self, anahtar: str) -> bytes: ...
    def sil(self, anahtar: str) -> None: ...


class YerelDepolama:
    def __init__(self, kok: Path):
        self.kok = kok.resolve()

    def _yol(self, anahtar: str) -> Path:
        yol = (self.kok / anahtar).resolve()
        if not yol.is_relative_to(self.kok):
            raise ValueError("Geçersiz depolama anahtarı.")
        return yol

    def kaydet(self, anahtar: str, veri: bytes) -> None:
        yol = self._yol(anahtar)
        yol.parent.mkdir(parents=True, exist_ok=True)
        # Yarım yazılmış dosya kalmaması için önce geçici dosyaya yazılır
        gecici = yol.with_name(yol.name + ".yaziliyor")
        gecici.write_bytes(veri)
        os.replace(gecici, yol)

    def oku(self, anahtar: str) -> bytes:
        return self._yol(anahtar).read_bytes()

    def sil(self, anahtar: str) -> None:
        self._yol(anahtar).unlink(missing_ok=True)


class SifreliDepolama:
    """Dosyayı yazmadan önce şifreler, okurken çözer (AES-256-GCM, AAD = depolama anahtarı).

    Şifresiz dosya okunmaz, hata verir: eski şifresiz dosyalar
    araclar/belgeleri_sifrele.py ile bir kez şifrelenir.
    """

    def __init__(self, alt: Depolama):
        self.alt = alt

    def kaydet(self, anahtar: str, veri: bytes) -> None:
        self.alt.kaydet(anahtar, kripto.belge_sifrele(veri, anahtar=anahtar))

    def oku(self, anahtar: str) -> bytes:
        return kripto.belge_coz(self.alt.oku(anahtar), anahtar=anahtar)

    def sil(self, anahtar: str) -> None:
        self.alt.sil(anahtar)


def varsayilan_depolama() -> Depolama:
    return SifreliDepolama(YerelDepolama(ayarlar.depolama_koku()))
