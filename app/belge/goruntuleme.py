"""Belge listeleme ve görüntüleme.

Her başarılı görüntüleme bir denetim kaydı oluşturur:
- dava dosyasındaki belge listesi: 'goruntuleme', hedef 'belge_listesi' (dava kimliği)
- belge ayrıntısı: 'goruntuleme', hedef 'belge'
- sayfa metni: 'goruntuleme', hedef 'belge_sayfa'
- orijinal dosyanın indirilmesi: 'disa_aktarim', hedef 'belge'

OCR ile okunmuş sayfalarda güven skoru eşiğin altındaysa ya da skor yoksa
(boş görünen ya da okunamayan sayfa) "aslıyla karşılaştırın" uyarısı döner.
"""

from uuid import UUID

from sqlalchemy import Connection, text

from app import ayarlar
from app.belge.depolama import Depolama
from app.belge.erisim import BelgeHatasi, belge_erisimini_denetle, dava_erisimini_denetle, denetim_yaz

UYARI_METNI = "Bu sayfa taranmış görüntüden OCR ile okundu; metni belgenin aslıyla karşılaştırın."


def _uyari_gerekli(metin_kaynagi: str, guven: float | None) -> bool:
    return metin_kaynagi == "ocr" and (guven is None or guven < ayarlar.OCR_UYARI_ESIGI)


def belgeleri_listele(
    conn: Connection,
    *,
    dava_id: UUID,
    kullanici_id: UUID,
    limit: int,
    offset: int,
    ip_adresi: str | None,
) -> dict:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    toplam = conn.execute(
        text("SELECT count(*) FROM belge WHERE dava_dosyasi_id = :d"), {"d": dava_id}
    ).scalar_one()
    satirlar = conn.execute(
        text(
            "SELECT b.id, b.orijinal_ad, b.mime_tur, b.durum, b.sayfa_sayisi, b.kategori, "
            "b.belge_tarihi, b.yuklenme, "
            "count(s.id) FILTER (WHERE s.metin_kaynagi = 'ocr') AS ocr_sayfa_sayisi, "
            "count(s.id) FILTER (WHERE s.metin_kaynagi = 'ocr' "
            "    AND (s.ocr_guven_skoru IS NULL OR s.ocr_guven_skoru < :esik)) AS uyarili_sayfa_sayisi "
            "FROM belge b LEFT JOIN belge_sayfa s ON s.belge_id = b.id "
            "WHERE b.dava_dosyasi_id = :d "
            "GROUP BY b.id ORDER BY b.yuklenme DESC, b.id "
            "LIMIT :limit OFFSET :offset"
        ),
        {"d": dava_id, "esik": ayarlar.OCR_UYARI_ESIGI, "limit": limit, "offset": offset},
    ).mappings().all()
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="belge_listesi", hedef_id=dava_id, ip_adresi=ip_adresi)
    return {"toplam": toplam, "limit": limit, "offset": offset, "belgeler": [dict(s) for s in satirlar]}


def belge_ayrintisi(conn: Connection, *, belge_id: UUID, kullanici_id: UUID, ip_adresi: str | None) -> dict:
    belge = belge_erisimini_denetle(conn, belge_id, kullanici_id)
    sayfalar = conn.execute(
        text(
            "SELECT sayfa_no, metin_kaynagi, ocr_guven_skoru, length(metin) AS karakter_sayisi "
            "FROM belge_sayfa WHERE belge_id = :b ORDER BY sayfa_no"
        ),
        {"b": belge_id},
    ).mappings().all()
    gorevler = conn.execute(
        text(
            "SELECT adim, durum, tekrar_sayisi, hata_mesaji, baslangic, bitis "
            "FROM isleme_gorevi WHERE belge_id = :b ORDER BY baslangic NULLS LAST, adim"
        ),
        {"b": belge_id},
    ).mappings().all()
    denetim_yaz(conn, buro_id=belge.buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="belge", hedef_id=belge_id, ip_adresi=ip_adresi)
    return {
        "id": belge.id,
        "dava_dosyasi_id": belge.dava_dosyasi_id,
        "orijinal_ad": belge.orijinal_ad,
        "mime_tur": belge.mime_tur,
        "sha256_ozet": belge.sha256_ozet,
        "sayfa_sayisi": belge.sayfa_sayisi,
        "kategori": belge.kategori,
        "belge_tarihi": belge.belge_tarihi,
        "durum": belge.durum,
        "yukleyen_kullanici_id": belge.yukleyen_kullanici_id,
        "yuklenme": belge.yuklenme,
        "sayfalar": [
            {**s, "asliyla_karsilastir": _uyari_gerekli(s["metin_kaynagi"], s["ocr_guven_skoru"])}
            for s in sayfalar
        ],
        "gorevler": [dict(g) for g in gorevler],
    }


def sayfa_metni(
    conn: Connection, *, belge_id: UUID, sayfa_no: int, kullanici_id: UUID, ip_adresi: str | None
) -> dict:
    belge = belge_erisimini_denetle(conn, belge_id, kullanici_id)
    sayfa = conn.execute(
        text(
            "SELECT id, sayfa_no, metin, metin_kaynagi, ocr_guven_skoru FROM belge_sayfa "
            "WHERE belge_id = :b AND sayfa_no = :n"
        ),
        {"b": belge_id, "n": sayfa_no},
    ).one_or_none()
    if sayfa is None:
        raise BelgeHatasi(404, "Sayfa bulunamadı.")
    denetim_yaz(conn, buro_id=belge.buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="belge_sayfa", hedef_id=sayfa.id, ip_adresi=ip_adresi)
    uyari = _uyari_gerekli(sayfa.metin_kaynagi, sayfa.ocr_guven_skoru)
    return {
        "belge_id": belge_id,
        "sayfa_no": sayfa.sayfa_no,
        "metin": sayfa.metin,
        "metin_kaynagi": sayfa.metin_kaynagi,
        "ocr_guven_skoru": sayfa.ocr_guven_skoru,
        "asliyla_karsilastir": uyari,
        "uyari": UYARI_METNI if uyari else None,
    }


def orijinal_dosya(
    conn: Connection, depolama: Depolama, *, belge_id: UUID, kullanici_id: UUID, ip_adresi: str | None
) -> tuple[bytes, str, str]:
    """(içerik, mime türü, orijinal ad) döndürür."""
    belge = belge_erisimini_denetle(conn, belge_id, kullanici_id)
    veri = depolama.oku(belge.depolama_anahtari)
    denetim_yaz(conn, buro_id=belge.buro_id, kullanici_id=kullanici_id, eylem="disa_aktarim",
                hedef_tur="belge", hedef_id=belge_id, ip_adresi=ip_adresi)
    return veri, belge.mime_tur, belge.orijinal_ad
