"""Büro yöneticisinin kullanıcı ve büro ayarları işlemleri (yönetim ekranının servis katmanı).

Kurallar:
- Yalnızca 'yonetici' rolü ve yalnızca kendi bürosu. Başka büronun kullanıcısı "bulunamadı" döner.
- Yönetici parola belirlemez; tek kullanımlık geçici parola üretilir, yanıtta BİR KEZ gösterilir ve
  hiçbir yere yazılmaz. Kullanıcı ilk girişte parolasını değiştirmek zorundadır.
- Yönetici kendi rolünü düşüremez, kendini pasifleştiremez; büroda her zaman en az bir aktif
  yönetici kalır (aksi halde büro yönetilemez hale gelir).
- Pasifleştirme ve geçici parola, kullanıcının açık oturumlarını kapatır. E-postası (giriş adı)
  değiştirilen kullanıcının oturumları da kapanır; yönetici kendi e-postasını değiştirirse oturumu sürer.
- Kullanıcı adı/e-postası ve büro adı değişikliği denetime eski ve yeni değeriyle yazılır.
- Analiz yalnızca bu bilgisayarda kurulu yerel modelle açılabilir (bulut sağlayıcı KVKK
  değerlendirmesi tamamlanmadan eklenmeyecek).
- Her işlem denetim kaydına yazılır; geçici parolanın kendisi yazılmaz.
"""

from uuid import UUID

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app.analiz.modeller import yerel_modeller
from app.belge.erisim import BelgeHatasi, ErisimReddi
from app.denetim import denetim_yaz
from app.kimlik import oturum, parola as parola_mod

ROLLER = {"yonetici", "avukat", "stajyer"}
YETKI_YOK = "Bu işlem yalnızca büro yöneticisine açıktır."
BULUNAMADI = "Kullanıcı bulunamadı."


def yonetici_burosu(conn: Connection, kullanici_id: UUID) -> UUID:
    k = conn.execute(text("SELECT buro_id, rol FROM kullanici WHERE id = :k"), {"k": kullanici_id}).one()
    if k.rol != "yonetici":
        raise ErisimReddi(403, YETKI_YOK, "yetki_yok")
    return k.buro_id


def _hedef(conn: Connection, buro_id: UUID, hedef_id: UUID):
    k = conn.execute(text("SELECT id, buro_id, rol, aktif, e_posta FROM kullanici WHERE id = :k FOR UPDATE"),
                     {"k": hedef_id}).one_or_none()
    if k is None or k.buro_id != buro_id:
        raise ErisimReddi(404, BULUNAMADI, "bulunamadi")
    return k


def kullanicilari_listele(conn: Connection, *, yonetici_id: UUID) -> list[dict]:
    buro_id = yonetici_burosu(conn, yonetici_id)
    return [dict(s) for s in conn.execute(
        text(
            "SELECT id, ad_soyad, e_posta, rol, aktif, parola_ozet IS NOT NULL AS parolasi_var, "
            "parola_degismeli, coalesce(kilit_bitis > now(), false) AS kilitli, kilit_bitis, son_giris, olusturma "
            "FROM kullanici WHERE buro_id = :b ORDER BY aktif DESC, ad_soyad"
        ),
        {"b": buro_id},
    ).mappings()]


def kullanici_olustur(
    conn: Connection, *, yonetici_id: UUID, ad_soyad: str, e_posta: str, rol: str, ip_adresi: str | None,
) -> dict:
    buro_id = yonetici_burosu(conn, yonetici_id)
    if rol not in ROLLER:
        raise BelgeHatasi(422, "Geçersiz rol.")
    e_posta, ad_soyad = e_posta.strip().lower(), ad_soyad.strip()
    if not ad_soyad or "@" not in e_posta:
        raise BelgeHatasi(422, "Ad soyad ve geçerli bir e-posta gerekli.")
    gecici = parola_mod.gecici_parola_uret()
    try:
        with conn.begin_nested():
            yeni_id = conn.execute(
                text("INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol, parola_ozet, parola_degisim, "
                     "parola_degismeli) VALUES (:b, :a, :e, :r, :p, now(), true) RETURNING id"),
                {"b": buro_id, "a": ad_soyad, "e": e_posta, "r": rol, "p": parola_mod.ozetle(gecici)},
            ).scalar_one()
    except IntegrityError:
        raise BelgeHatasi(409, "Bu e-posta adresiyle kayıtlı bir hesap zaten var.")
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="olusturma", hedef_tur="kullanici",
                hedef_id=yeni_id, ip_adresi=ip_adresi, ayrinti={"rol": rol})
    return {"id": yeni_id, "gecici_parola": gecici}


def gecici_parola_ver(conn: Connection, *, yonetici_id: UUID, hedef_id: UUID, ip_adresi: str | None) -> dict:
    buro_id = yonetici_burosu(conn, yonetici_id)
    hedef = _hedef(conn, buro_id, hedef_id)
    if hedef.id == yonetici_id:
        raise BelgeHatasi(422, "Kendi parolanızı \"Parolamı değiştir\" sayfasından değiştirin.")
    gecici = parola_mod.gecici_parola_uret()
    conn.execute(
        text("UPDATE kullanici SET parola_ozet = :p, parola_degisim = now(), parola_degismeli = true, "
             "basarisiz_giris = 0, kilit_bitis = NULL WHERE id = :k"),
        {"p": parola_mod.ozetle(gecici), "k": hedef.id},
    )
    kapanan = oturum.tum_oturumlari_kapat(conn, hedef.id)
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="guncelleme", hedef_tur="kullanici",
                hedef_id=hedef.id, ip_adresi=ip_adresi, ayrinti={"islem": "gecici_parola", "kapanan_oturum": kapanan})
    return {"gecici_parola": gecici, "kapanan_oturum": kapanan}


def kilit_ac(conn: Connection, *, yonetici_id: UUID, hedef_id: UUID, ip_adresi: str | None) -> None:
    buro_id = yonetici_burosu(conn, yonetici_id)
    hedef = _hedef(conn, buro_id, hedef_id)
    conn.execute(text("UPDATE kullanici SET basarisiz_giris = 0, kilit_bitis = NULL WHERE id = :k"), {"k": hedef.id})
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="guncelleme", hedef_tur="kullanici",
                hedef_id=hedef.id, ip_adresi=ip_adresi, ayrinti={"islem": "kilit_ac"})


def kullanici_guncelle(
    conn: Connection, *, yonetici_id: UUID, hedef_id: UUID, rol: str | None, aktif: bool | None,
    ip_adresi: str | None,
) -> None:
    buro_id = yonetici_burosu(conn, yonetici_id)
    hedef = _hedef(conn, buro_id, hedef_id)
    if rol is not None and rol not in ROLLER:
        raise BelgeHatasi(422, "Geçersiz rol.")
    yeni_rol = rol if rol is not None else hedef.rol
    yeni_aktif = aktif if aktif is not None else hedef.aktif
    if hedef.id == yonetici_id and (yeni_rol != "yonetici" or not yeni_aktif):
        raise BelgeHatasi(422, "Kendi yönetici yetkinizi kaldıramaz, hesabınızı pasifleştiremezsiniz.")
    if hedef.rol == "yonetici" and hedef.aktif and (yeni_rol != "yonetici" or not yeni_aktif):
        # Diğer yöneticiler kilitlenerek sayılır: eşzamanlı iki işlem son iki yöneticiyi birden düşüremez
        digerleri = conn.execute(
            text("SELECT count(*) FROM (SELECT id FROM kullanici WHERE buro_id = :b AND rol = 'yonetici' "
                 "AND aktif AND id <> :k FOR UPDATE) y"),
            {"b": buro_id, "k": hedef.id},
        ).scalar_one()
        if digerleri == 0:
            raise BelgeHatasi(422, "Büroda en az bir aktif yönetici kalmalı.")
    degisen = {}
    if yeni_rol != hedef.rol:
        degisen["rol"] = [hedef.rol, yeni_rol]
    if yeni_aktif != hedef.aktif:
        degisen["aktif"] = [hedef.aktif, yeni_aktif]
    if not degisen:
        return
    conn.execute(text("UPDATE kullanici SET rol = :r, aktif = :a WHERE id = :k"),
                 {"r": yeni_rol, "a": yeni_aktif, "k": hedef.id})
    if not yeni_aktif or "rol" in degisen:
        # Yetki değişince eski yetkiyle açılmış oturum kalmasın
        degisen["kapanan_oturum"] = oturum.tum_oturumlari_kapat(conn, hedef.id)
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="erisim_degisikligi",
                hedef_tur="kullanici", hedef_id=hedef.id, ip_adresi=ip_adresi, ayrinti=degisen)


def kullanici_bilgisi_degistir(
    conn: Connection, *, yonetici_id: UUID, hedef_id: UUID, ad_soyad: str | None, e_posta: str | None,
    ip_adresi: str | None,
) -> None:
    buro_id = yonetici_burosu(conn, yonetici_id)
    hedef = _hedef(conn, buro_id, hedef_id)
    eski_ad = conn.execute(text("SELECT ad_soyad FROM kullanici WHERE id = :k"), {"k": hedef.id}).scalar_one()
    yeni_ad = ad_soyad.strip() if ad_soyad is not None else eski_ad
    yeni_e_posta = e_posta.strip().lower() if e_posta is not None else hedef.e_posta
    if not yeni_ad or "@" not in yeni_e_posta:
        raise BelgeHatasi(422, "Ad soyad ve geçerli bir e-posta gerekli.")
    degisen = {}
    if yeni_ad != eski_ad:
        degisen["ad_soyad"] = [eski_ad, yeni_ad]
    if yeni_e_posta != hedef.e_posta:
        degisen["e_posta"] = [hedef.e_posta, yeni_e_posta]
    if not degisen:
        return
    baska = conn.execute(text("SELECT 1 FROM kullanici WHERE lower(e_posta) = :e AND id <> :k"),
                         {"e": yeni_e_posta, "k": hedef.id}).first()
    if baska:
        raise BelgeHatasi(409, "Bu e-posta adresiyle kayıtlı bir hesap zaten var.")
    try:
        with conn.begin_nested():
            conn.execute(text("UPDATE kullanici SET ad_soyad = :a, e_posta = :e WHERE id = :k"),
                         {"a": yeni_ad, "e": yeni_e_posta, "k": hedef.id})
    except IntegrityError:
        raise BelgeHatasi(409, "Bu e-posta adresiyle kayıtlı bir hesap zaten var.")
    if "e_posta" in degisen and hedef.id != yonetici_id:
        # Giriş adı değişti: kişi yeni e-postasıyla yeniden girer
        degisen["kapanan_oturum"] = oturum.tum_oturumlari_kapat(conn, hedef.id)
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="guncelleme", hedef_tur="kullanici",
                hedef_id=hedef.id, ip_adresi=ip_adresi, ayrinti=degisen)


def buro_adi_degistir(conn: Connection, *, yonetici_id: UUID, ad: str, ip_adresi: str | None) -> None:
    buro_id = yonetici_burosu(conn, yonetici_id)
    ad = " ".join(ad.split())
    if not ad:
        raise BelgeHatasi(422, "Büro adı boş olamaz.")
    eski = conn.execute(text("SELECT ad FROM buro WHERE id = :b FOR UPDATE"), {"b": buro_id}).scalar_one()
    if eski == ad:
        return
    conn.execute(text("UPDATE buro SET ad = :a WHERE id = :b"), {"a": ad, "b": buro_id})
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="guncelleme", hedef_tur="buro",
                hedef_id=buro_id, ip_adresi=ip_adresi, ayrinti={"ad": [eski, ad]})


def buro_ayarlari(conn: Connection, *, yonetici_id: UUID) -> dict:
    buro_id = yonetici_burosu(conn, yonetici_id)
    b = conn.execute(text("SELECT id, ad, analiz_modeli FROM buro WHERE id = :b"), {"b": buro_id}).one()
    modeller = yerel_modeller()
    return {"id": b.id, "ad": b.ad, "analiz_modeli": b.analiz_modeli,
            "yerel_modeller": [f"ollama:{m}" for m in modeller] if modeller is not None else None}


def analiz_modelini_ayarla(conn: Connection, *, yonetici_id: UUID, model: str | None, ip_adresi: str | None) -> None:
    buro_id = yonetici_burosu(conn, yonetici_id)
    if model is not None:
        if not model.startswith("ollama:"):
            raise BelgeHatasi(422, "Şimdilik yalnızca bu bilgisayarda çalışan yerel modeller kullanılabilir.")
        kurulu = yerel_modeller()
        if kurulu is None:
            raise BelgeHatasi(503, "Yerel model sunucusuna (Ollama) ulaşılamadı; analiz açılamadı.")
        if model.removeprefix("ollama:") not in kurulu:
            raise BelgeHatasi(422, "Bu model bu bilgisayarda kurulu değil.")
    onceki = conn.execute(text("SELECT analiz_modeli FROM buro WHERE id = :b FOR UPDATE"),
                          {"b": buro_id}).scalar_one()
    if onceki == model:
        return
    conn.execute(text("UPDATE buro SET analiz_modeli = :m WHERE id = :b"), {"b": buro_id, "m": model})
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="guncelleme", hedef_tur="buro",
                hedef_id=buro_id, ip_adresi=ip_adresi, ayrinti={"analiz_modeli": [onceki, model]})
