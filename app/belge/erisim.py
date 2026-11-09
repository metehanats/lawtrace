"""Belge modülünün ortak erişim denetimi ve denetim kaydı.

Erişim kuralı: kullanıcı aktif olmalı, dava dosyasıyla aynı büroda olmalı ve ya
büro yöneticisi olmalı ya da o dosya için dosya_erisim kaydı bulunmalıdır.
Başka büronun dosyası "bulunamadı" ile aynı biçimde reddedilir; böylece var olduğu sızmaz.

Kapalı dosya salt okunurdur: yazma=True ile çağrılan işlemler (belge yükleme, analiz, bulgu ve
çelişki kararları, özel nitelik) dosya yeniden açılana kadar 409 ile reddedilir.

Reddedilen denemeler ErisimReddi olarak yükseltilir ve HTTP katmanında, isteğin
geri alınan işleminden bağımsız olarak denetime yazılır (erisim_reddi_kaydet).
"""

from uuid import UUID

from sqlalchemy import Connection, text

from app.denetim import denetim_yaz  # noqa: F401  (belge modülü bu adla da kullanıyor)


class BelgeHatasi(Exception):
    """HTTP durum koduyla eşleşen iş kuralı hatası."""

    def __init__(self, kod: int, mesaj: str):
        super().__init__(mesaj)
        self.kod = kod
        self.mesaj = mesaj


class ErisimReddi(BelgeHatasi):
    """Erişim denetiminin reddettiği istek. neden: 'yetki_yok' ya da 'bulunamadi'.

    'bulunamadi', hedefin hiç olmamasını da başka büroya ait olmasını da kapsar;
    kullanıcının kendi bürosunun denetim kaydına bu ikisinin farkı yazılmaz.
    """

    def __init__(self, kod: int, mesaj: str, neden: str):
        super().__init__(kod, mesaj)
        self.neden = neden


DAVA_BULUNAMADI = "Dava dosyası bulunamadı."
DOSYA_KAPALI = "Dava dosyası kapalı; değişiklik için önce dosyayı yeniden açın."
BELGE_BULUNAMADI = "Belge bulunamadı."


def dava_erisimini_denetle(
    conn: Connection, dava_id: UUID, kullanici_id: UUID, bulunamadi: str = DAVA_BULUNAMADI, *, yazma: bool = False
) -> UUID:
    """Kullanıcının dava dosyasına erişebildiğini doğrular ve büro kimliğini döndürür.

    yazma=True: dosya kapalıysa reddeder. Satır kilitlenir; böylece eşzamanlı kapatma ile
    bir yazma işlemi arasında yarış olmaz.
    """
    dava = conn.execute(
        text("SELECT buro_id, durum FROM dava_dosyasi WHERE id = :d" + (" FOR SHARE" if yazma else "")),
        {"d": dava_id},
    ).one_or_none()
    if dava is None:
        raise ErisimReddi(404, bulunamadi, "bulunamadi")

    kullanici = conn.execute(
        text(
            "SELECT k.buro_id, k.rol, k.aktif, e.rol AS erisim_rolu "
            "FROM kullanici k "
            "LEFT JOIN dosya_erisim e ON e.kullanici_id = k.id AND e.dava_dosyasi_id = :d "
            "WHERE k.id = :k"
        ),
        {"d": dava_id, "k": kullanici_id},
    ).one_or_none()
    if kullanici is None or not kullanici.aktif or kullanici.buro_id != dava.buro_id:
        raise ErisimReddi(404, bulunamadi, "bulunamadi")
    if kullanici.rol != "yonetici" and kullanici.erisim_rolu is None:
        raise ErisimReddi(403, "Bu dava dosyasına erişim yetkiniz yok.", "yetki_yok")
    if yazma and dava.durum == "kapali":
        raise BelgeHatasi(409, DOSYA_KAPALI)
    return dava.buro_id


def belge_erisimini_denetle(conn: Connection, belge_id: UUID, kullanici_id: UUID, *, yazma: bool = False):
    """Kullanıcının belgeye erişebildiğini doğrular ve belge kaydını döndürür."""
    belge = conn.execute(
        text(
            "SELECT id, buro_id, dava_dosyasi_id, orijinal_ad, mime_tur, depolama_anahtari, "
            "sha256_ozet, sayfa_sayisi, kategori, belge_tarihi, durum, yukleyen_kullanici_id, yuklenme "
            "FROM belge WHERE id = :b"
        ),
        {"b": belge_id},
    ).one_or_none()
    if belge is None:
        raise ErisimReddi(404, BELGE_BULUNAMADI, "bulunamadi")
    dava_erisimini_denetle(conn, belge.dava_dosyasi_id, kullanici_id, bulunamadi=BELGE_BULUNAMADI, yazma=yazma)
    return belge


def erisim_reddi_kaydet(
    conn: Connection,
    reddi: ErisimReddi,
    *,
    kullanici_id: UUID,
    istenen_eylem: str,
    hedef_tur: str,
    hedef_id: UUID | None,
    ip_adresi: str | None,
    ek: dict | None = None,
) -> bool:
    """Reddedilen denemeyi, deneyen kullanıcının bürosunun denetim kaydına yazar.

    Kullanıcı tanınmıyorsa (ör. geçersiz kimlik) kayıt büroya bağlanamaz ve yazılmaz;
    False döner. Kimlik doğrulama eklendiğinde kullanıcı her zaman tanınır olacak.
    """
    buro_id = conn.execute(
        text("SELECT buro_id FROM kullanici WHERE id = :k"), {"k": kullanici_id}
    ).scalar_one_or_none()
    if buro_id is None:
        return False
    denetim_yaz(
        conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="erisim_reddi",
        hedef_tur=hedef_tur, hedef_id=hedef_id, ip_adresi=ip_adresi,
        ayrinti={"neden": reddi.neden, "istenen_eylem": istenen_eylem, "durum_kodu": reddi.kod, **(ek or {})},
    )
    return True
