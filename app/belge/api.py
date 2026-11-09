"""Belge modülünün HTTP uçları. Tüm uçlar oturum açmış kullanıcı gerektirir."""

import logging
import unicodedata
from collections.abc import Callable
from contextlib import AbstractContextManager
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request, Response, UploadFile
from sqlalchemy import Connection

from app import ayarlar
from app.belge import goruntuleme
from app.belge.depolama import Depolama, varsayilan_depolama
from app.belge.erisim import BelgeHatasi, ErisimReddi, erisim_reddi_kaydet
from app.belge.yukleme import belge_yukle
from app.db import baglanti, engine
from app.kimlik.api import gecerli_kullanici
from app.web import istemci_ip as _istemci_ip

router = APIRouter(tags=["belge"])
gunluk = logging.getLogger("app.belge.api")

IslemAc = Callable[[], AbstractContextManager[Connection]]


def depolama_al() -> Depolama:
    return varsayilan_depolama()


def ayri_islem() -> IslemAc:
    """İstekten bağımsız bir işlem (transaction) açar.

    Reddedilen istekte isteğin işlemi geri alınır; red kaydı da aynı işlemde yazılsaydı
    onunla birlikte silinirdi. Bu yüzden red kaydı ayrı bir işlemde yazılır.
    """
    return engine().begin


class RedKaydedici:
    """BelgeHatasi'nı HTTP yanıtına çevirir; erişim reddiyse önce denetime yazar."""

    def __init__(self, request: Request, kullanici_id: UUID, islem_ac: IslemAc):
        self.ip = _istemci_ip(request)
        self.kullanici_id = kullanici_id
        self.islem_ac = islem_ac

    def hata(
        self, hata: BelgeHatasi, *, istenen_eylem: str, hedef_tur: str, hedef_id: UUID | None,
        ek: dict | None = None,
    ) -> HTTPException:
        if isinstance(hata, ErisimReddi):
            try:
                with self.islem_ac() as conn:
                    erisim_reddi_kaydet(
                        conn, hata, kullanici_id=self.kullanici_id, istenen_eylem=istenen_eylem,
                        hedef_tur=hedef_tur, hedef_id=hedef_id, ip_adresi=self.ip, ek=ek,
                    )
            except Exception:
                # Kaydın yazılamaması kullanıcıya verilen yanıtı değiştirmez; ama fark edilmeli
                gunluk.exception("Erişim reddi denetim kaydına yazılamadı (hedef %s %s).", hedef_tur, hedef_id)
        return HTTPException(status_code=hata.kod, detail=hata.mesaj)


def red_kaydedici(
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    islem_ac: IslemAc = Depends(ayri_islem),
) -> RedKaydedici:
    return RedKaydedici(request, kullanici_id, islem_ac)


@router.post("/davalar/{dava_id}/belgeler", status_code=201)
async def belge_yukle_ucu(
    dava_id: UUID,
    dosya: UploadFile,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    depolama: Depolama = Depends(depolama_al),
    red: RedKaydedici = Depends(red_kaydedici),
):
    # Sınırın bir bayt fazlası okunur; böylece büyük dosya belleğe tamamen alınmadan reddedilir
    veri = await dosya.read(ayarlar.MAKS_BELGE_BOYUTU + 1)
    try:
        return belge_yukle(
            conn,
            depolama,
            dava_id=dava_id,
            kullanici_id=kullanici_id,
            orijinal_ad=dosya.filename or "adsiz",
            veri=veri,
            ip_adresi=_istemci_ip(request),
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="yukleme", hedef_tur="dava_dosyasi", hedef_id=dava_id)


@router.get("/davalar/{dava_id}/belgeler")
def belgeleri_listele_ucu(
    dava_id: UUID,
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return goruntuleme.belgeleri_listele(
            conn, dava_id=dava_id, kullanici_id=kullanici_id, limit=limit, offset=offset,
            ip_adresi=_istemci_ip(request),
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="belge_listesi", hedef_id=dava_id)


@router.get("/belgeler/{belge_id}")
def belge_ayrintisi_ucu(
    belge_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return goruntuleme.belge_ayrintisi(
            conn, belge_id=belge_id, kullanici_id=kullanici_id, ip_adresi=_istemci_ip(request)
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="belge", hedef_id=belge_id)


@router.get("/belgeler/{belge_id}/sayfalar/{sayfa_no}")
def sayfa_metni_ucu(
    belge_id: UUID,
    request: Request,
    sayfa_no: int = Path(ge=1),
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        return goruntuleme.sayfa_metni(
            conn, belge_id=belge_id, sayfa_no=sayfa_no, kullanici_id=kullanici_id,
            ip_adresi=_istemci_ip(request),
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="goruntuleme", hedef_tur="belge", hedef_id=belge_id,
                       ek={"sayfa_no": sayfa_no})


def _icerik_basligi(ad: str) -> str:
    """İndirme için Content-Disposition başlığı.

    Dosya adı yükleyenden gelir; başlık enjeksiyonunu önlemek için denetim karakterleri
    atılır. Türkçe karakterli ad RFC 5987 ile (filename*), eski tarayıcılar için ASCII
    karşılığıyla (filename) verilir.
    """
    temiz = "".join(c for c in ad if unicodedata.category(c)[0] != "C").strip() or "belge"
    ascii_ad = unicodedata.normalize("NFKD", temiz.replace("ı", "i").replace("İ", "I"))
    ascii_ad = ascii_ad.encode("ascii", "ignore").decode().replace('"', "").replace("\\", "") or "belge"
    return f"attachment; filename=\"{ascii_ad}\"; filename*=UTF-8''{quote(temiz, safe='')}"


@router.get("/belgeler/{belge_id}/dosya")
def orijinal_dosya_ucu(
    belge_id: UUID,
    request: Request,
    kullanici_id: UUID = Depends(gecerli_kullanici),
    conn: Connection = Depends(baglanti),
    depolama: Depolama = Depends(depolama_al),
    red: RedKaydedici = Depends(red_kaydedici),
):
    try:
        veri, mime_tur, ad = goruntuleme.orijinal_dosya(
            conn, depolama, belge_id=belge_id, kullanici_id=kullanici_id, ip_adresi=_istemci_ip(request)
        )
    except BelgeHatasi as hata:
        raise red.hata(hata, istenen_eylem="disa_aktarim", hedef_tur="belge", hedef_id=belge_id)
    return Response(
        content=veri,
        media_type=mime_tur,
        headers={
            "Content-Disposition": _icerik_basligi(ad),
            # Müvekkil belgesi tarayıcı ya da ara sunucu önbelleğinde kalmamalı
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )
