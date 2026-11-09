"""Uygulama katmanında şifreleme: müvekkil kimlik/iletişim alanları ve belge dosyaları.

- Ana anahtar MUVEKKIL_ANAHTARI ortam değişkenindedir (32 bayt, base64url). Veritabanında
  ve proje dosyalarında anahtar yoktur; veritabanı dökümü ve belge klasörü tek başına okunamaz.
  Anahtar kaybolursa şifreli veriler KALICI olarak açılamaz: anahtarın ayrı ve güvenli bir yedeği şarttır.
- Ana anahtardan HKDF ile ayrı anahtarlar türetilir: alan şifreleme (AES-256-GCM),
  arama özeti (HMAC-SHA256) ve belge dosyası şifreleme (AES-256-GCM).
- Şifreli değer biçimi: b"v1" + 12 bayt nonce + şifreli metin ve etiket. Ek doğrulama
  verisi (AAD) kaydın kimliği ve alan adıdır; bir değer başka kayda ya da alana
  taşınırsa çözülemez.
- Anahtar değiştirme (rotasyon) henüz yok; sürüm öneki ("v1") ileride buna yer bırakır.

Yeni anahtar üretmek için: python -m app.kripto anahtar-uret
Kayıtlı anahtarın izi (yedeğini doğrulamak için): python -m app.kripto parmak-izi
"""

import base64
import hashlib
import hmac
import os
import secrets
import sys
from functools import lru_cache
from uuid import UUID

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

SURUM = b"v1"


class AnahtarYok(RuntimeError):
    pass


def _ana_anahtar() -> bytes:
    deger = os.environ.get("MUVEKKIL_ANAHTARI")
    if not deger:
        raise AnahtarYok(
            "MUVEKKIL_ANAHTARI ortam değişkeni tanımlı değil. Üretmek için: python -m app.kripto anahtar-uret"
        )
    anahtar = base64.urlsafe_b64decode(deger.encode() + b"=" * (-len(deger) % 4))
    if len(anahtar) != 32:
        raise AnahtarYok("MUVEKKIL_ANAHTARI 32 bayt olmalı.")
    return anahtar


@lru_cache(maxsize=4)
def _turet(ana: bytes, amac: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"avukat-dosya-takip/" + amac).derive(ana)


def _sifreleme_anahtari() -> bytes:
    return _turet(_ana_anahtar(), b"sifreleme")


def _ozet_anahtari() -> bytes:
    return _turet(_ana_anahtar(), b"arama-ozeti")


def _aad(kayit_id: UUID, alan: str) -> bytes:
    return f"{kayit_id}:{alan}".encode()


def sifrele(metin: str, *, kayit_id: UUID, alan: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return SURUM + nonce + AESGCM(_sifreleme_anahtari()).encrypt(nonce, metin.encode(), _aad(kayit_id, alan))


def coz(veri: bytes, *, kayit_id: UUID, alan: str) -> str:
    veri = bytes(veri)
    if veri[:2] != SURUM:
        raise ValueError("Bilinmeyen şifreleme sürümü.")
    nonce, sifreli = veri[2:14], veri[14:]
    return AESGCM(_sifreleme_anahtari()).decrypt(nonce, sifreli, _aad(kayit_id, alan)).decode()


BELGE_SURUMU = b"ADT1"


def _bayt_sifrele(veri: bytes, *, amac: bytes, aad: str) -> bytes:
    nonce = secrets.token_bytes(12)
    return BELGE_SURUMU + nonce + AESGCM(_turet(_ana_anahtar(), amac)).encrypt(nonce, veri, aad.encode())


def _bayt_coz(veri: bytes, *, amac: bytes, aad: str) -> bytes:
    if veri[:4] != BELGE_SURUMU:
        raise ValueError("Dosya şifreli değil ya da şifreleme sürümü bilinmiyor.")
    return AESGCM(_turet(_ana_anahtar(), amac)).decrypt(veri[4:16], veri[16:], aad.encode())


def belge_sifrele(veri: bytes, *, anahtar: str) -> bytes:
    """Belge dosyası şifreleme. AAD depolama anahtarıdır: dosya başka belgenin yerine konamaz."""
    return _bayt_sifrele(veri, amac=b"belge-depolama", aad=anahtar)


def belge_coz(veri: bytes, *, anahtar: str) -> bytes:
    return _bayt_coz(veri, amac=b"belge-depolama", aad=anahtar)


def belge_sifreli_mi(veri: bytes) -> bool:
    return veri[:4] == BELGE_SURUMU


def yedek_sifrele(veri: bytes, *, ad: str) -> bytes:
    """Veritabanı dökümü gibi yedek dosyaları; belge anahtarından ayrı türetilmiş anahtarla."""
    return _bayt_sifrele(veri, amac=b"yedek", aad=ad)


def yedek_coz(veri: bytes, *, ad: str) -> bytes:
    return _bayt_coz(veri, amac=b"yedek", aad=ad)


def anahtar_parmak_izi() -> str:
    """Anahtarı açık etmeden tanıtan kısa iz: kaydedilen yedeğin doğru anahtar olduğunu denetlemek için."""
    return hashlib.sha256(_turet(_ana_anahtar(), b"parmak-izi")).hexdigest()[:16]


def arama_ozeti(metin: str, *, alan: str) -> str:
    """Aynı değer için hep aynı sonucu veren anahtarlı özet (mükerrer kayıt denetimi için)."""
    return hmac.new(_ozet_anahtari(), f"{alan}:{metin}".encode(), hashlib.sha256).hexdigest()


def anahtar_uret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode().rstrip("=")


if __name__ == "__main__":
    if sys.argv[1:] == ["anahtar-uret"]:
        print(anahtar_uret())
    elif sys.argv[1:] == ["parmak-izi"]:
        print(anahtar_parmak_izi())
    else:
        print("Kullanım: python -m app.kripto anahtar-uret | parmak-izi", file=sys.stderr)
        sys.exit(1)
