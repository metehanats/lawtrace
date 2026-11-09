"""Büro yöneticisi uçları (/yonetim). Kurallar app/kimlik/yonetici.py içinde."""

from datetime import date, datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection

from app import ayarlar, yedek
from app.belge.api import RedKaydedici, red_kaydedici
from app.belge.erisim import BelgeHatasi
from app.db import baglanti
from app.kimlik import denetim_ekrani, yonetici
from app.kimlik.api import gecerli_kullanici
from app.web import istemci_ip

router = APIRouter(prefix="/yonetim", tags=["yonetim"])

Rol = Literal["yonetici", "avukat", "stajyer"]


def _gizli(govde: dict, kod: int = 200) -> JSONResponse:
    """Geçici parola içeren yanıt: tarayıcı ya da ara sunucu önbelleğe almasın."""
    return JSONResponse(status_code=kod, content={k: str(v) if isinstance(v, UUID) else v for k, v in govde.items()},
                        headers={"Cache-Control": "no-store"})


@router.get("/kullanicilar")
def kullanicilari_listele(
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return {"kullanicilar": yonetici.kullanicilari_listele(conn, yonetici_id=kullanici_id)}
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="kullanici_listesi", hedef_id=None)


class YeniKullanici(BaseModel):
    ad_soyad: str = Field(min_length=2, max_length=200)
    e_posta: str = Field(min_length=3, max_length=254)
    rol: Rol


@router.post("/kullanicilar", status_code=201)
def kullanici_olustur(
    istek: YeniKullanici, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return _gizli(yonetici.kullanici_olustur(conn, yonetici_id=kullanici_id, ad_soyad=istek.ad_soyad,
                                                 e_posta=istek.e_posta, rol=istek.rol,
                                                 ip_adresi=istemci_ip(request)), 201)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="olusturma", hedef_tur="kullanici", hedef_id=None)


class KullaniciGuncelleme(BaseModel):
    rol: Rol | None = None
    aktif: bool | None = None
    ad_soyad: str | None = Field(default=None, min_length=1, max_length=200)
    e_posta: str | None = Field(default=None, min_length=3, max_length=254)


@router.patch("/kullanicilar/{hedef_id}", status_code=204)
def kullanici_guncelle(
    hedef_id: UUID, istek: KullaniciGuncelleme, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        if istek.ad_soyad is not None or istek.e_posta is not None:
            yonetici.kullanici_bilgisi_degistir(conn, yonetici_id=kullanici_id, hedef_id=hedef_id,
                                                ad_soyad=istek.ad_soyad, e_posta=istek.e_posta,
                                                ip_adresi=istemci_ip(request))
        if istek.rol is not None or istek.aktif is not None:
            yonetici.kullanici_guncelle(conn, yonetici_id=kullanici_id, hedef_id=hedef_id, rol=istek.rol,
                                        aktif=istek.aktif, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        eylem = "erisim_degisikligi" if istek.rol is not None or istek.aktif is not None else "guncelleme"
        raise red.hata(hata, istenen_eylem=eylem, hedef_tur="kullanici", hedef_id=hedef_id)


@router.post("/kullanicilar/{hedef_id}/gecici-parola")
def gecici_parola_ver(
    hedef_id: UUID, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return _gizli(yonetici.gecici_parola_ver(conn, yonetici_id=kullanici_id, hedef_id=hedef_id,
                                                 ip_adresi=istemci_ip(request)))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="kullanici", hedef_id=hedef_id)


@router.post("/kullanicilar/{hedef_id}/kilit-ac", status_code=204)
def kilit_ac(
    hedef_id: UUID, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        yonetici.kilit_ac(conn, yonetici_id=kullanici_id, hedef_id=hedef_id, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="kullanici", hedef_id=hedef_id)


@router.get("/buro")
def buro_ayarlari(
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return yonetici.buro_ayarlari(conn, yonetici_id=kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="buro", hedef_id=None)


@router.get("/denetim")
def denetim_listele(
    request: Request,
    kullanici: UUID | None = None,
    eylem: list[str] | None = Query(default=None),
    baslangic: date | None = None,
    bitis: date | None = None,
    once: int | None = None,
    limit: int = 50,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return denetim_ekrani.kayitlari_listele(
            conn, yonetici_id=kullanici_id, ip_adresi=istemci_ip(request), kullanici_id=kullanici, eylemler=eylem,
            baslangic=baslangic, bitis=bitis, once=once, limit=limit)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="denetim_kaydi", hedef_id=None)


@router.get("/denetim/ozet")
def denetim_ozeti(
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return denetim_ekrani.ozet(conn, yonetici_id=kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="denetim_kaydi", hedef_id=None)


@router.get("/denetim/disa-aktar")
def denetim_disa_aktar(
    request: Request,
    kullanici: UUID | None = None,
    eylem: list[str] | None = Query(default=None),
    baslangic: date | None = None,
    bitis: date | None = None,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        icerik = denetim_ekrani.disa_aktar(conn, yonetici_id=kullanici_id, ip_adresi=istemci_ip(request),
                                           kullanici_id=kullanici, eylemler=eylem, baslangic=baslangic, bitis=bitis)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="disa_aktarim", hedef_tur="denetim_kaydi", hedef_id=None)
    ad = f"denetim-kaydi-{datetime.now():%Y%m%d-%H%M}.csv"
    return Response(content=icerik.encode("utf-8"), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{ad}"', "Cache-Control": "no-store"})


@router.get("/yedek")
def yedek_durumu(
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    """Son otomatik yedeğin durumu (yedek-gunlugu.jsonl). Yedek bu sunucunun diskinde olduğu için buradan okunur."""
    try:
        yonetici.yonetici_burosu(conn, kullanici_id)
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="yedek", hedef_id=None)
    d = yedek.durum(ayarlar.yedek_klasoru())
    son = d["son_basarili"]
    yas = (datetime.now().astimezone() - datetime.fromisoformat(son["zaman"])).total_seconds() / 3600 if son else None
    # Günlük yedek: 36 saatten eski başarılı yedek ya da son denemenin hata vermesi uyarıdır
    d["uyari"] = son is None or yas > 36 or (d["son_deneme"] or {}).get("durum") == "hata"
    return d


class BuroAdi(BaseModel):
    ad: str = Field(min_length=1, max_length=200)


@router.put("/buro/ad", status_code=204)
def buro_adi_degistir(
    istek: BuroAdi, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        yonetici.buro_adi_degistir(conn, yonetici_id=kullanici_id, ad=istek.ad, ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="buro", hedef_id=None)


class AnalizAyari(BaseModel):
    analiz_modeli: str | None = Field(default=None, max_length=200)   # None: analiz kapalı


@router.put("/buro/analiz", status_code=204)
def analiz_ayarla(
    istek: AnalizAyari, request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici), conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        yonetici.analiz_modelini_ayarla(conn, yonetici_id=kullanici_id, model=istek.analiz_modeli,
                                        ip_adresi=istemci_ip(request))
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="guncelleme", hedef_tur="buro", hedef_id=None)
