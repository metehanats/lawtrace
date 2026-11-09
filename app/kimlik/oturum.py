"""Giriş, oturum doğrulama ve çıkış.

- Girişte rastgele bir belirteç üretilir ve tarayıcıya HttpOnly çerez olarak verilir.
  Veritabanında belirtecin yalnızca SHA-256 özeti tutulur.
- Oturum en fazla OTURUM_SURESI_SAAT sürer; OTURUM_BOSTA_DAKIKA boyunca kullanılmazsa kapanır.
- Art arda GIRIS_KILIT_ESIGI hatalı girişte hesap GIRIS_KILIT_DAKIKA kilitlenir.
- Tüm başarısız girişlerde aynı genel mesaj döner; hesabın var olup olmadığı,
  kilitli ya da pasif olduğu dışarıdan anlaşılmaz. Ayrıntı denetim kaydına yazılır.
"""

import hashlib
import secrets
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import Connection, text

from app import ayarlar
from app.denetim import denetim_yaz
from app.kimlik import parola as parola_mod

GENEL_HATA = "E-posta veya parola hatalı."


def belirtec_ozeti(belirtec: str) -> str:
    return hashlib.sha256(belirtec.encode()).hexdigest()


@dataclass
class GirisSonucu:
    belirtec: str
    kullanici_id: UUID
    buro_id: UUID


def _basarisiz_say(conn: Connection, kullanici_id: UUID) -> bool:
    """Hatalı parola sayacını artırır; eşiğe ulaşınca hesabı kilitler. Kilitlendiyse True."""
    return conn.execute(
        text(
            "UPDATE kullanici SET "
            "basarisiz_giris = CASE WHEN basarisiz_giris + 1 >= :esik THEN 0 ELSE basarisiz_giris + 1 END, "
            "kilit_bitis = CASE WHEN basarisiz_giris + 1 >= :esik "
            "    THEN now() + make_interval(secs => :sn) ELSE kilit_bitis END "
            "WHERE id = :k RETURNING basarisiz_giris = 0 AS kilitlendi"
        ),
        {"k": kullanici_id, "esik": ayarlar.GIRIS_KILIT_ESIGI, "sn": ayarlar.GIRIS_KILIT_DAKIKA * 60},
    ).scalar_one()


def giris(
    conn: Connection, *, e_posta: str, parola: str, ip_adresi: str | None, kullanici_araci: str | None
) -> GirisSonucu | None:
    """Başarılıysa yeni oturumu, değilse None döndürür. Başarısız deneme sayacı da günceller.

    Çağıran, başarısızlıkta da işlemi onaylamalıdır (sayaç ve denetim kaydı kalıcı olmalı).
    """
    kullanici = conn.execute(
        text(
            "SELECT id, buro_id, parola_ozet, aktif, basarisiz_giris, "
            "kilit_bitis IS NOT NULL AND kilit_bitis > now() AS kilitli "
            "FROM kullanici WHERE lower(e_posta) = lower(:e) FOR UPDATE"
        ),
        {"e": e_posta.strip()},
    ).one_or_none()

    # Parola her durumda doğrulanır (bilinmeyen, kilitli, pasif hesapta da); böylece yanıt
    # süresinden hesabın varlığı ya da durumu anlaşılmaz
    dogru = parola_mod.dogrula(kullanici.parola_ozet if kullanici else None, parola)
    if kullanici is None:
        return None

    def basarisiz(neden: str, sayaci_artir: bool = True) -> None:
        ayrinti = {"neden": neden}
        if sayaci_artir and _basarisiz_say(conn, kullanici.id):
            ayrinti["hesap_kilitlendi"] = True
        denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici.id, eylem="giris_basarisiz",
                    hedef_tur="kullanici", hedef_id=kullanici.id, ip_adresi=ip_adresi, ayrinti=ayrinti)

    if kullanici.kilitli:
        # Kilitliyken yapılan denemeler kilidi uzatmaz, ama kaydedilir
        basarisiz("kilitli", sayaci_artir=False)
        return None
    if not kullanici.aktif:
        basarisiz("pasif_hesap", sayaci_artir=False)
        return None
    if kullanici.parola_ozet is None:
        basarisiz("parola_tanimsiz", sayaci_artir=False)
        return None
    if not dogru:
        basarisiz("yanlis_parola")
        return None

    yeni_ozet = parola_mod.ozetle(parola) if parola_mod.yeniden_ozetlenmeli(kullanici.parola_ozet) else None
    conn.execute(
        text(
            "UPDATE kullanici SET basarisiz_giris = 0, kilit_bitis = NULL, son_giris = now(), "
            "parola_ozet = coalesce(:yeni, parola_ozet) WHERE id = :k"
        ),
        {"k": kullanici.id, "yeni": yeni_ozet},
    )
    belirtec = secrets.token_urlsafe(32)
    oturum_id = conn.execute(
        text(
            "INSERT INTO oturum (kullanici_id, belirtec_ozet, bitis, ip_adresi, kullanici_araci) "
            "VALUES (:k, :o, now() + make_interval(secs => :sn), :ip, :arac) RETURNING id"
        ),
        {
            "k": kullanici.id, "o": belirtec_ozeti(belirtec), "sn": ayarlar.OTURUM_SURESI_SAAT * 3600,
            "ip": ip_adresi, "arac": (kullanici_araci or "")[:300] or None,
        },
    ).scalar_one()
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici.id, eylem="giris",
                hedef_tur="oturum", hedef_id=oturum_id, ip_adresi=ip_adresi)
    return GirisSonucu(belirtec, kullanici.id, kullanici.buro_id)


def oturumu_dogrula(conn: Connection, belirtec: str) -> UUID | None:
    """Geçerli oturumun kullanıcısını döndürür ve son kullanım zamanını yeniler."""
    return conn.execute(
        text(
            "UPDATE oturum o SET son_kullanim = now() FROM kullanici k "
            "WHERE o.belirtec_ozet = :o AND k.id = o.kullanici_id AND k.aktif "
            "AND o.iptal IS NULL AND o.bitis > now() "
            "AND o.son_kullanim > now() - make_interval(secs => :bosta) "
            "RETURNING o.kullanici_id"
        ),
        {"o": belirtec_ozeti(belirtec), "bosta": ayarlar.OTURUM_BOSTA_DAKIKA * 60},
    ).scalar_one_or_none()


def cikis(conn: Connection, belirtec: str, ip_adresi: str | None) -> bool:
    oturum = conn.execute(
        text(
            "UPDATE oturum o SET iptal = now() FROM kullanici k "
            "WHERE o.belirtec_ozet = :o AND o.iptal IS NULL AND k.id = o.kullanici_id "
            "RETURNING o.id, o.kullanici_id, k.buro_id"
        ),
        {"o": belirtec_ozeti(belirtec)},
    ).one_or_none()
    if oturum is None:
        return False
    denetim_yaz(conn, buro_id=oturum.buro_id, kullanici_id=oturum.kullanici_id, eylem="cikis",
                hedef_tur="oturum", hedef_id=oturum.id, ip_adresi=ip_adresi)
    return True


class ParolaHatasi(Exception):
    def __init__(self, mesaj: str, *, oturum_kapandi: bool = False):
        super().__init__(mesaj)
        self.oturum_kapandi = oturum_kapandi


def parola_degistir(
    conn: Connection, *, kullanici_id: UUID, mevcut: str, yeni: str, belirtec: str, ip_adresi: str | None,
) -> None:
    """Kullanıcının kendi parolasını değiştirmesi. Bu oturum açık kalır, diğerleri kapanır.

    Yanlış "mevcut parola" girişle aynı sayaca yazılır: oturumu ele geçiren biri burada parola
    tahmin edemesin. Eşiğe ulaşılınca hesap kilitlenir ve bu oturum dahil tüm oturumlar kapanır.
    Çağıran, hata durumunda da işlemi onaylamalıdır (sayaç ve denetim kaydı kalıcı olmalı).
    """
    k = conn.execute(text("SELECT e_posta, buro_id, parola_ozet FROM kullanici WHERE id = :k FOR UPDATE"),
                     {"k": kullanici_id}).one()
    if not parola_mod.dogrula(k.parola_ozet, mevcut):
        kilitlendi = _basarisiz_say(conn, kullanici_id)
        ayrinti = {"neden": "parola_degisiminde_yanlis_parola", **({"hesap_kilitlendi": True} if kilitlendi else {})}
        denetim_yaz(conn, buro_id=k.buro_id, kullanici_id=kullanici_id, eylem="giris_basarisiz",
                    hedef_tur="kullanici", hedef_id=kullanici_id, ip_adresi=ip_adresi, ayrinti=ayrinti)
        if kilitlendi:
            tum_oturumlari_kapat(conn, kullanici_id)
            raise ParolaHatasi("Çok sayıda hatalı deneme: hesap geçici olarak kilitlendi ve oturum kapatıldı.",
                               oturum_kapandi=True)
        raise ParolaHatasi("Mevcut parola hatalı.")
    if yeni == mevcut:
        raise ParolaHatasi("Yeni parola mevcut paroladan farklı olmalı.")
    if sorun := parola_mod.parola_sorunu(yeni, k.e_posta):
        raise ParolaHatasi(sorun)
    conn.execute(
        text("UPDATE kullanici SET parola_ozet = :p, parola_degisim = now(), parola_degismeli = false "
             "WHERE id = :k"),
        {"p": parola_mod.ozetle(yeni), "k": kullanici_id},
    )
    conn.execute(
        text("UPDATE oturum SET iptal = now() WHERE kullanici_id = :k AND iptal IS NULL AND belirtec_ozet <> :o"),
        {"k": kullanici_id, "o": belirtec_ozeti(belirtec)},
    )
    denetim_yaz(conn, buro_id=k.buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="kullanici",
                hedef_id=kullanici_id, ip_adresi=ip_adresi, ayrinti={"islem": "parola_degisimi"})


def tum_oturumlari_kapat(conn: Connection, kullanici_id: UUID) -> int:
    """Parola değişince ya da hesap kapatılınca kullanıcının açık oturumlarını sonlandırır."""
    return conn.execute(
        text("UPDATE oturum SET iptal = now() WHERE kullanici_id = :k AND iptal IS NULL"),
        {"k": kullanici_id},
    ).rowcount
