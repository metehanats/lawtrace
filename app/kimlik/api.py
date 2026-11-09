"""Kimlik doğrulama uçları ve oturum bağımlılığı.

Oturum belirteci yalnızca HttpOnly çerezde taşınır; yanıt gövdesinde dönmez,
böylece sayfadaki JavaScript (ve olası bir XSS) belirteci okuyamaz.
CSRF: çerez SameSite=Lax; başka sitelerden gelen POST isteklerine çerez eklenmez.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import Connection, text

from app import ayarlar
from app.db import baglanti
from app.kimlik import oturum
from app.web import istemci_ip

router = APIRouter(prefix="/oturum", tags=["oturum"])

OTURUM_YOK = "Oturum açmanız gerekiyor."
PAROLA_DEGISMELI = "Devam etmeden önce parolanızı değiştirmeniz gerekiyor."


def oturumdaki_kullanici(request: Request, conn: Connection = Depends(baglanti)) -> UUID:
    """Geçerli oturumun kullanıcısı; parola değiştirme zorunluluğuna bakmaz.

    Yalnızca /oturum/ben ve /oturum/parola kullanır. Diğer tüm uçlar gecerli_kullanici ister.
    """
    belirtec = request.cookies.get(ayarlar.OTURUM_COOKIE_ADI)
    kullanici_id = oturum.oturumu_dogrula(conn, belirtec) if belirtec else None
    if kullanici_id is None:
        raise HTTPException(status_code=401, detail=OTURUM_YOK)
    return kullanici_id


def gecerli_kullanici(
    kullanici_id: UUID = Depends(oturumdaki_kullanici), conn: Connection = Depends(baglanti),
) -> UUID:
    # Geçici parolayla giren kullanıcı, parolasını değiştirene kadar başka hiçbir işlem yapamaz
    if conn.execute(text("SELECT parola_degismeli FROM kullanici WHERE id = :k"), {"k": kullanici_id}).scalar_one():
        raise HTTPException(status_code=403, detail=PAROLA_DEGISMELI)
    return kullanici_id


class GirisIstegi(BaseModel):
    e_posta: str = Field(min_length=3, max_length=254)
    # Üst sınır, çok uzun parolalarla özetleme maliyeti üzerinden yapılacak saldırıları önler
    parola: str = Field(min_length=1, max_length=1024)


def _kullanici_bilgisi(conn: Connection, kullanici_id: UUID) -> dict:
    satir = conn.execute(
        text(
            "SELECT k.id, k.ad_soyad, k.e_posta, k.rol, k.parola_degismeli, b.id AS buro_id, b.ad AS buro_adi "
            "FROM kullanici k JOIN buro b ON b.id = k.buro_id WHERE k.id = :k"
        ),
        {"k": kullanici_id},
    ).mappings().one()
    return dict(satir)


@router.post("/giris")
def giris_ucu(istek: GirisIstegi, request: Request, conn: Connection = Depends(baglanti)):
    sonuc = oturum.giris(
        conn, e_posta=istek.e_posta, parola=istek.parola,
        ip_adresi=istemci_ip(request), kullanici_araci=request.headers.get("user-agent"),
    )
    if sonuc is None:
        # İstisna yerine yanıt döndürülür: böylece istek işlemi onaylanır ve başarısız
        # deneme sayacı ile denetim kaydı kalıcı olur
        return JSONResponse(status_code=401, content={"detail": oturum.GENEL_HATA},
                            headers={"Cache-Control": "no-store"})
    yanit = JSONResponse(content={"kullanici": _jsonla(_kullanici_bilgisi(conn, sonuc.kullanici_id))},
                         headers={"Cache-Control": "no-store"})
    yanit.set_cookie(
        ayarlar.OTURUM_COOKIE_ADI, sonuc.belirtec,
        max_age=int(ayarlar.OTURUM_SURESI_SAAT * 3600),
        httponly=True, secure=ayarlar.OTURUM_COOKIE_GUVENLI, samesite="lax", path="/",
    )
    return yanit


@router.post("/cikis", status_code=204)
def cikis_ucu(request: Request, conn: Connection = Depends(baglanti)):
    belirtec = request.cookies.get(ayarlar.OTURUM_COOKIE_ADI)
    if belirtec:
        oturum.cikis(conn, belirtec, istemci_ip(request))
    yanit = Response(status_code=204)
    yanit.delete_cookie(ayarlar.OTURUM_COOKIE_ADI, path="/", httponly=True,
                        secure=ayarlar.OTURUM_COOKIE_GUVENLI, samesite="lax")
    return yanit


@router.get("/ben")
def ben_ucu(kullanici_id: UUID = Depends(oturumdaki_kullanici), conn: Connection = Depends(baglanti)):
    return _kullanici_bilgisi(conn, kullanici_id)


class ParolaIstegi(BaseModel):
    mevcut: str = Field(min_length=1, max_length=1024)
    yeni: str = Field(min_length=1, max_length=1024)


@router.post("/parola", status_code=204)
def parola_ucu(
    istek: ParolaIstegi, request: Request,
    kullanici_id: UUID = Depends(oturumdaki_kullanici), conn: Connection = Depends(baglanti),
):
    try:
        oturum.parola_degistir(conn, kullanici_id=kullanici_id, mevcut=istek.mevcut, yeni=istek.yeni,
                               belirtec=request.cookies[ayarlar.OTURUM_COOKIE_ADI], ip_adresi=istemci_ip(request))
    except oturum.ParolaHatasi as hata:
        # İstisna yerine yanıt: işlem onaylanır, hatalı deneme sayacı ve denetim kaydı kalıcı olur
        if hata.oturum_kapandi:
            yanit = JSONResponse(status_code=401, content={"detail": str(hata)})
            yanit.delete_cookie(ayarlar.OTURUM_COOKIE_ADI, path="/", httponly=True,
                                secure=ayarlar.OTURUM_COOKIE_GUVENLI, samesite="lax")
            return yanit
        return JSONResponse(status_code=422, content={"detail": str(hata)})
    return Response(status_code=204)


def _jsonla(sozluk: dict) -> dict:
    return {k: str(v) if isinstance(v, UUID) else v for k, v in sozluk.items()}
