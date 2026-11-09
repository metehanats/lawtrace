"""Parola özetleme (Argon2id) ve parola kuralları."""

import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app import ayarlar

_hasher = PasswordHasher()

# Bilinmeyen e-postayla gelen girişte de bir özet doğrulanır; böylece yanıt süresinden
# e-postanın kayıtlı olup olmadığı anlaşılmaz.
SAHTE_OZET = _hasher.hash("bu-parola-hicbir-hesaba-ait-degil")


def ozetle(parola: str) -> str:
    return _hasher.hash(parola)


def dogrula(ozet: str | None, parola: str) -> bool:
    try:
        return _hasher.verify(ozet or SAHTE_OZET, parola) and ozet is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def yeniden_ozetlenmeli(ozet: str) -> bool:
    """Özetleme ayarları güçlendirildiyse eski özet girişte yenilenir."""
    return _hasher.check_needs_rehash(ozet)


_GECICI_ALFABE = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKMNPQRSTUVWXYZ23456789"   # karışan 0/O, 1/l/I yok


def gecici_parola_uret() -> str:
    """Yöneticinin kullanıcıya ileteceği tek kullanımlık parola (ör. "k7Pm-x3Qa-9vRt-Hn2c")."""
    while True:
        parola = "-".join("".join(secrets.choice(_GECICI_ALFABE) for _ in range(4)) for _ in range(4))
        if parola_sorunu(parola) is None:
            return parola


def parola_sorunu(parola: str, e_posta: str | None = None) -> str | None:
    """Parola kurallara uymuyorsa nedenini, uyuyorsa None döndürür."""
    if len(parola) < ayarlar.PAROLA_EN_AZ_UZUNLUK:
        return f"Parola en az {ayarlar.PAROLA_EN_AZ_UZUNLUK} karakter olmalı."
    if parola.strip() != parola:
        return "Parola boşlukla başlayamaz ya da bitemez."
    if e_posta and e_posta.split("@")[0].lower() in parola.lower():
        return "Parola e-posta adresinizi içermemeli."
    if len(set(parola)) < 5:
        return "Parola çok tekdüze; daha çeşitli karakterler kullanın."
    return None
