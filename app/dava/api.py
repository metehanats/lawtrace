"""Dava dosyası, müvekkil ve büro kullanıcısı uçları.

Yönetici bürodaki tüm dosyaları, diğer roller yalnızca dosya_erisim kaydı olan
dosyaları görür (kural app/belge/erisim.py ile aynı). Oluşturma ve erişim yönetimi
kuralları app/dava/hizmet.py içinde.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import ayarlar
from app.belge.api import RedKaydedici, red_kaydedici
from app.dava import hizmet
from app.belge.erisim import BelgeHatasi, dava_erisimini_denetle
from app.db import baglanti
from app.denetim import denetim_yaz
from app.kimlik.api import gecerli_kullanici
from app.web import istemci_ip

router = APIRouter(prefix="/davalar", tags=["dava"])

_DAVA_ALANLARI = (
    "d.id, d.dosya_no, d.baslik, d.dava_turu, d.durum, d.olusturma, d.guncelleme, "
    "d.muvekkil_id, m.ad_unvan AS muvekkil, "
    "(SELECT count(*) FROM belge b WHERE b.dava_dosyasi_id = d.id) AS belge_sayisi, "
    "(SELECT count(*) FROM belge b WHERE b.dava_dosyasi_id = d.id AND b.durum IN ('yuklendi', 'isleniyor')) "
    "    AS islenen_belge_sayisi, "
    # Dosyada avukatı bekleyen işler (dava listesindeki "Bekleyen" sütunu; Özet sekmesiyle aynı tanımlar)
    "(SELECT count(*) FROM bulgu bu WHERE bu.dava_dosyasi_id = d.id AND bu.dogrulama_durumu = 'otomatik') "
    "    AS incelenmemis_bulgu, "
    "(SELECT count(*) FROM uyusmazlik u WHERE u.dava_dosyasi_id = d.id AND u.durum = 'acik') AS acik_celiski, "
    "(SELECT count(*) FROM belge_sayfa s JOIN belge b ON b.id = s.belge_id WHERE b.dava_dosyasi_id = d.id "
    "    AND s.metin_kaynagi = 'ocr' AND (s.ocr_guven_skoru IS NULL OR s.ocr_guven_skoru < :esik)) "
    "    AS kontrol_ocr_sayfa, "
    "(SELECT count(*) FROM belge b WHERE b.dava_dosyasi_id = d.id AND b.ozel_nitelikli "
    "    AND b.ozel_nitelik_onay_zamani IS NULL) AS onay_bekleyen_belge"
)


@router.get("")
def davalari_listele(
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
):
    kullanici = conn.execute(
        text("SELECT buro_id, rol FROM kullanici WHERE id = :k"), {"k": kullanici_id}
    ).one()
    satirlar = conn.execute(
        text(
            f"SELECT {_DAVA_ALANLARI}, e.rol AS erisim_rolu "
            "FROM dava_dosyasi d JOIN muvekkil m ON m.id = d.muvekkil_id "
            "LEFT JOIN dosya_erisim e ON e.dava_dosyasi_id = d.id AND e.kullanici_id = :k "
            "WHERE d.buro_id = :b AND (:yonetici OR e.kullanici_id IS NOT NULL) "
            "ORDER BY d.guncelleme DESC, d.dosya_no"
        ),
        {"k": kullanici_id, "b": kullanici.buro_id, "yonetici": kullanici.rol == "yonetici",
         "esik": ayarlar.OCR_UYARI_ESIGI},
    ).mappings().all()
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="dava_listesi", hedef_id=None, ip_adresi=istemci_ip(request))
    return {"davalar": [dict(s) for s in satirlar]}


@router.get("/{dava_id}")
def dava_ayrintisi(
    dava_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)
    satir = conn.execute(
        text(f"SELECT {_DAVA_ALANLARI} FROM dava_dosyasi d JOIN muvekkil m ON m.id = d.muvekkil_id "
             "WHERE d.id = :d"),
        {"d": dava_id, "esik": ayarlar.OCR_UYARI_ESIGI},
    ).mappings().one()
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="dava_dosyasi", hedef_id=dava_id, ip_adresi=istemci_ip(request))
    kullanici = hizmet.kullanici_al(conn, kullanici_id)
    return {**satir, "duzenleyebilir": hizmet.dava_duzenleyebilir_mi(conn, dava_id, kullanici)}


class DavaIstegi(BaseModel):
    muvekkil_id: UUID
    dosya_no: str = Field(min_length=1, max_length=60)
    baslik: str = Field(min_length=1, max_length=300)
    dava_turu: str | None = Field(default=None, max_length=100)


@router.post("", status_code=201)
def dava_olustur(
    istek: DavaIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.dava_olustur(conn, kullanici_id=kullanici_id, ip_adresi=istemci_ip(request),
                                   **istek.model_dump())
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="olusturma", hedef_tur="dava_dosyasi", hedef_id=None)


class DavaGuncelleme(DavaIstegi):
    durum: str = Field(pattern="^(acik|beklemede|kapali)$")


@router.put("/{dava_id}", status_code=204)
def dava_guncelle(
    dava_id: UUID,
    istek: DavaGuncelleme,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.dava_guncelle(conn, kullanici_id=kullanici_id, dava_id=dava_id, ip_adresi=istemci_ip(request),
                             **istek.model_dump())
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)


@router.get("/{dava_id}/erisimler")
def erisimleri_listele(
    dava_id: UUID,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.erisimleri_listele(conn, dava_id=dava_id, kullanici_id=kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)


class ErisimIstegi(BaseModel):
    rol: str = Field(pattern="^(sorumlu|inceleyen)$")


@router.put("/{dava_id}/erisimler/{hedef_id}", status_code=204)
def erisim_ver(
    dava_id: UUID,
    hedef_id: UUID,
    istek: ErisimIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.erisim_ver(conn, dava_id=dava_id, kullanici_id=kullanici_id, hedef_id=hedef_id, rol=istek.rol,
                          ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="erisim_degisikligi", hedef_tur="dava_dosyasi", hedef_id=dava_id,
                       ek={"kullanici_id": str(hedef_id)})


@router.delete("/{dava_id}/erisimler/{hedef_id}", status_code=204)
def erisim_kaldir(
    dava_id: UUID,
    hedef_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.erisim_kaldir(conn, dava_id=dava_id, kullanici_id=kullanici_id, hedef_id=hedef_id,
                             ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="erisim_degisikligi", hedef_tur="dava_dosyasi", hedef_id=dava_id,
                       ek={"kullanici_id": str(hedef_id)})


# --- Müvekkiller ve büro kullanıcıları -------------------------------------

muvekkil_router = APIRouter(prefix="/muvekkiller", tags=["muvekkil"])


class MuvekkilIstegi(BaseModel):
    tur: str = Field(pattern="^(gercek_kisi|tuzel_kisi)$")
    ad_unvan: str = Field(min_length=1, max_length=300)
    kimlik_no: str | None = Field(default=None, max_length=20)
    telefon: str | None = Field(default=None, max_length=40)
    e_posta: str | None = Field(default=None, max_length=254)
    adres: str | None = Field(default=None, max_length=500)


@muvekkil_router.get("")
def muvekkilleri_listele(
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
):
    return {"muvekkiller": hizmet.muvekkilleri_listele(conn, kullanici_id=kullanici_id,
                                                         ip_adresi=istemci_ip(request))}


@muvekkil_router.post("", status_code=201)
def muvekkil_olustur(
    istek: MuvekkilIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.muvekkil_olustur(
            conn, kullanici_id=kullanici_id, tur=istek.tur, ad_unvan=istek.ad_unvan, kimlik_no=istek.kimlik_no,
            iletisim={"telefon": istek.telefon, "e_posta": istek.e_posta, "adres": istek.adres},
            ip_adresi=istemci_ip(request),
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="olusturma", hedef_tur="muvekkil", hedef_id=None)


@muvekkil_router.get("/{muvekkil_id}")
def muvekkil_ayrintisi(
    muvekkil_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.muvekkil_ayrintisi(conn, muvekkil_id=muvekkil_id, kullanici_id=kullanici_id,
                                         ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="muvekkil", hedef_id=muvekkil_id)


@muvekkil_router.put("/{muvekkil_id}", status_code=204)
def muvekkil_guncelle(
    muvekkil_id: UUID,
    istek: MuvekkilIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.muvekkil_guncelle(
            conn, kullanici_id=kullanici_id, muvekkil_id=muvekkil_id, tur=istek.tur, ad_unvan=istek.ad_unvan,
            kimlik_no=istek.kimlik_no,
            iletisim={"telefon": istek.telefon, "e_posta": istek.e_posta, "adres": istek.adres},
            ip_adresi=istemci_ip(request),
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="muvekkil", hedef_id=muvekkil_id)


kullanici_router = APIRouter(prefix="/kullanicilar", tags=["kullanici"])


@kullanici_router.get("")
def buro_kullanicilari(kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti)):
    return {"kullanicilar": hizmet.buro_kullanicilari(conn, kullanici_id=kullanici_id)}
