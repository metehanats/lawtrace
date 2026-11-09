"""Belge yükleme: tür denetimi, erişim denetimi (erisim.py), sha256 özeti, depolama ve kayıt.

Başarılı her yükleme için bir metin çıkarma görevi ve bir denetim kaydı oluşturulur.
"""

import hashlib
import io
import zipfile
from uuid import UUID, uuid4

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app import ayarlar
from app.belge.depolama import Depolama, anahtar_olustur
from app.belge.erisim import BelgeHatasi, dava_erisimini_denetle, denetim_yaz

PDF = "application/pdf"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


class YuklemeHatasi(BelgeHatasi):
    pass


def tur_belirle(veri: bytes) -> str | None:
    """Dosya türünü uzantıya ya da istemcinin bildirdiği türe göre değil, içeriğe göre belirler."""
    if veri.startswith(b"%PDF-"):
        return PDF
    if veri.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(veri)) as z:
                if "word/document.xml" in z.namelist():
                    return DOCX
        except zipfile.BadZipFile:
            return None
    return None


def belge_yukle(
    conn: Connection,
    depolama: Depolama,
    *,
    dava_id: UUID,
    kullanici_id: UUID,
    orijinal_ad: str,
    veri: bytes,
    ip_adresi: str | None = None,
) -> dict:
    if not veri:
        raise YuklemeHatasi(400, "Dosya boş.")
    if len(veri) > ayarlar.MAKS_BELGE_BOYUTU:
        raise YuklemeHatasi(413, "Dosya boyutu sınırı aşıldı.")
    mime_tur = tur_belirle(veri)
    if mime_tur is None:
        raise YuklemeHatasi(415, "Yalnızca PDF ve Word (.docx) belgeleri kabul edilir.")

    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id, yazma=True)
    ozet = hashlib.sha256(veri).hexdigest()

    mevcut = conn.execute(
        text("SELECT id FROM belge WHERE dava_dosyasi_id = :d AND sha256_ozet = :o"),
        {"d": dava_id, "o": ozet},
    ).scalar_one_or_none()
    if mevcut is not None:
        raise YuklemeHatasi(409, f"Bu belge bu dava dosyasına daha önce yüklenmiş (belge {mevcut}).")

    belge_id = uuid4()
    anahtar = anahtar_olustur(buro_id, dava_id, belge_id)
    depolama.kaydet(anahtar, veri)
    try:
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO belge (id, buro_id, dava_dosyasi_id, orijinal_ad, mime_tur, "
                    "depolama_anahtari, sha256_ozet, yukleyen_kullanici_id) "
                    "VALUES (:id, :b, :d, :ad, :mime, :anahtar, :ozet, :k)"
                ),
                {
                    "id": belge_id, "b": buro_id, "d": dava_id, "ad": orijinal_ad,
                    "mime": mime_tur, "anahtar": anahtar, "ozet": ozet, "k": kullanici_id,
                },
            )
            gorev_id = conn.execute(
                text(
                    "INSERT INTO isleme_gorevi (belge_id, adim) VALUES (:b, 'metin_cikarma') RETURNING id"
                ),
                {"b": belge_id},
            ).scalar_one()
            denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="yukleme",
                        hedef_tur="belge", hedef_id=belge_id, ip_adresi=ip_adresi)
    except IntegrityError:
        # Eşzamanlı aynı yükleme gibi durumlarda kayıt oluşmaz; dosya da geri silinir
        depolama.sil(anahtar)
        raise YuklemeHatasi(409, "Bu belge bu dava dosyasına daha önce yüklenmiş.")
    except Exception:
        depolama.sil(anahtar)
        raise

    return {
        "id": belge_id,
        "mime_tur": mime_tur,
        "sha256_ozet": ozet,
        "durum": "yuklendi",
        "metin_cikarma_gorevi_id": gorev_id,
    }
