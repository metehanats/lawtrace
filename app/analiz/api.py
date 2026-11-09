"""Analiz ve bulgu uçları. Kurallar app/analiz/hizmet.py içinde."""

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app.analiz import hizmet
from app.belge.api import RedKaydedici, red_kaydedici
from app.belge.erisim import BelgeHatasi
from app.db import baglanti
from app.kimlik.api import gecerli_kullanici
from app.web import istemci_ip

router = APIRouter(tags=["analiz"])


class AnalizIstegi(BaseModel):
    # Boşsa dosyadaki tüm hazır belgeler
    belge_idleri: list[UUID] | None = None


@router.post("/davalar/{dava_id}/analiz", status_code=202)
def analiz_baslat(
    dava_id: UUID,
    istek: AnalizIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.analiz_baslat(conn, dava_id=dava_id, kullanici_id=kullanici_id,
                                    belge_idleri=istek.belge_idleri, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="analiz", hedef_tur="dava_dosyasi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/analiz")
def analiz_durumu(
    dava_id: UUID,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.analiz_durumu(conn, dava_id=dava_id, kullanici_id=kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/bulgular")
def bulgulari_listele(
    dava_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return {"bulgular": hizmet.bulgulari_listele(conn, dava_id=dava_id, kullanici_id=kullanici_id,
                                                     ip_adresi=istemci_ip(request))}
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="bulgu_listesi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/zaman-cizelgesi")
def zaman_cizelgesi(
    dava_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return {"olaylar": hizmet.zaman_cizelgesi(conn, dava_id=dava_id, kullanici_id=kullanici_id,
                                                  ip_adresi=istemci_ip(request))}
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="zaman_cizelgesi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/iddia-haritasi")
def iddia_haritasi(
    dava_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return {"dilekceler": hizmet.iddia_haritasi(conn, dava_id=dava_id, kullanici_id=kullanici_id,
                                                    ip_adresi=istemci_ip(request))}
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="iddia_haritasi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/celiskiler")
def celiskileri_listele(
    dava_id: UUID,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return {"celiskiler": hizmet.celiskileri_listele(conn, dava_id=dava_id, kullanici_id=kullanici_id)}
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)


class CeliskiDurumuIstegi(BaseModel):
    durum: str = Field(pattern="^(acik|incelendi|cozuldu)$")


@router.put("/celiskiler/{celiski_id}", status_code=204)
def celiski_durumu_degistir(
    celiski_id: UUID,
    istek: CeliskiDurumuIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.celiski_durumu_degistir(conn, celiski_id=celiski_id, kullanici_id=kullanici_id, durum=istek.durum,
                                       ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="uyusmazlik", hedef_id=celiski_id)


class IncelemeIstegi(BaseModel):
    karar: str = Field(pattern="^(onay|red)$")
    notu: str | None = Field(default=None, max_length=2000)


@router.post("/bulgular/{bulgu_id}/inceleme")
def bulgu_incele(
    bulgu_id: UUID,
    istek: IncelemeIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.bulgu_incele(conn, bulgu_id=bulgu_id, kullanici_id=kullanici_id, karar=istek.karar,
                                   notu=istek.notu, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="onay", hedef_tur="bulgu", hedef_id=bulgu_id)


class DuzeltmeIstegi(BaseModel):
    deger: str = Field(min_length=1, max_length=300)
    notu: str | None = Field(default=None, max_length=2000)


@router.post("/bulgular/{bulgu_id}/duzeltme")
def bulgu_duzelt(
    bulgu_id: UUID,
    istek: DuzeltmeIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.bulgu_duzelt(conn, bulgu_id=bulgu_id, kullanici_id=kullanici_id, deger=istek.deger,
                                   notu=istek.notu, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="bulgu", hedef_id=bulgu_id)


@router.get("/etiketler")
def etiket_secenekleri(kullanici_id: UUID = Depends(gecerli_kullanici)):
    return hizmet.etiket_secenekleri()


class EtiketIstegi(BaseModel):
    etiket: str | None = Field(default=None, max_length=60)   # None: etiketsiz


@router.put("/bulgular/{bulgu_id}/etiket")
def bulgu_etiketle(
    bulgu_id: UUID,
    istek: EtiketIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return hizmet.bulgu_etiketle(conn, bulgu_id=bulgu_id, kullanici_id=kullanici_id, etiket=istek.etiket,
                                     ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="bulgu", hedef_id=bulgu_id)


@router.post("/belgeler/{belge_id}/ozel-nitelik-onayi", status_code=204)
def ozel_nitelik_onayla(
    belge_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.ozel_nitelik_onayla(conn, belge_id=belge_id, kullanici_id=kullanici_id, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="onay", hedef_tur="belge", hedef_id=belge_id)


class IsaretIstegi(BaseModel):
    ozel_nitelikli: bool
    neden: str | None = Field(default=None, max_length=500)


@router.put("/belgeler/{belge_id}/ozel-nitelik", status_code=204)
def ozel_nitelik_isaretle(
    belge_id: UUID,
    istek: IsaretIstegi,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        hizmet.ozel_nitelik_isaretle(conn, belge_id=belge_id, kullanici_id=kullanici_id,
                                     isaretli=istek.ozel_nitelikli, neden=istek.neden,
                                     ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="belge", hedef_id=belge_id)
