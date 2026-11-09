"""Yönetici için denetim kaydı ekranı: süzgeçli liste, son 24 saat özeti ve CSV dışa aktarım.

Kurallar:
- Yalnızca yönetici ve yalnızca kendi bürosunun kayıtları.
- Hedef adı (dava no, belge adı, kullanıcı adı…) yalnızca hedef de AYNI BÜROYA aitse gösterilir.
  "bulunamadı" ile reddedilen bir deneme başka büronun dosyasını hedeflemiş olabilir; o dosyanın
  adı bu büroya hiçbir zaman açılmaz (yalnızca kimliği kayıtta durur).
- Kaydı görüntülemek de dışa aktarmak da denetim kaydına yazılır.
- Kayıt değiştirilemez ve silinemez; bu ekran yalnızca okur.
"""

import csv
import io
import json
from datetime import date
from uuid import UUID

from sqlalchemy import Connection, text

from app.belge.erisim import BelgeHatasi
from app.denetim import denetim_yaz
from app.kimlik.yonetici import yonetici_burosu

EYLEMLER = {
    "goruntuleme", "yukleme", "silme", "onay", "reddetme", "disa_aktarim", "erisim_reddi", "giris",
    "giris_basarisiz", "cikis", "olusturma", "erisim_degisikligi", "analiz", "guncelleme",
}
SAYFA_EN_COK = 200
DISA_AKTARIM_EN_COK = 10_000
SAAT_DILIMI = "Europe/Istanbul"

# Dava dosyasına bağlı liste ve görünümler: hedef_id dava kimliğidir
_DAVA_HEDEFLI = ("dava_dosyasi", "belge_listesi", "bulgu_listesi", "zaman_cizelgesi", "iddia_haritasi")

# Hedef adı, hedef aynı bürodaysa bulunur (her kolda buro_id = dk.buro_id)
_HEDEF = f"""
LEFT JOIN LATERAL (
    SELECT d.dosya_no || ' · ' || d.baslik AS ad, d.id AS dava_id, NULL::uuid AS belge_id FROM dava_dosyasi d
     WHERE dk.hedef_tur IN {_DAVA_HEDEFLI!r} AND d.id = dk.hedef_id AND d.buro_id = dk.buro_id
    UNION ALL
    SELECT be.orijinal_ad || ' (' || d.dosya_no || ')', d.id, be.id FROM belge be
      JOIN dava_dosyasi d ON d.id = be.dava_dosyasi_id
     WHERE dk.hedef_tur = 'belge' AND be.id = dk.hedef_id AND d.buro_id = dk.buro_id
    UNION ALL
    SELECT be.orijinal_ad || ' s. ' || s.sayfa_no, d.id, be.id FROM belge_sayfa s
      JOIN belge be ON be.id = s.belge_id JOIN dava_dosyasi d ON d.id = be.dava_dosyasi_id
     WHERE dk.hedef_tur = 'belge_sayfa' AND s.id = dk.hedef_id AND d.buro_id = dk.buro_id
    UNION ALL
    SELECT b.ozet || ' (' || d.dosya_no || ')', d.id, NULL FROM bulgu b JOIN dava_dosyasi d ON d.id = b.dava_dosyasi_id
     WHERE dk.hedef_tur = 'bulgu' AND b.id = dk.hedef_id AND d.buro_id = dk.buro_id
    UNION ALL
    SELECT 'Çelişki (' || d.dosya_no || ')', d.id, NULL FROM uyusmazlik u JOIN dava_dosyasi d ON d.id = u.dava_dosyasi_id
     WHERE dk.hedef_tur = 'uyusmazlik' AND u.id = dk.hedef_id AND d.buro_id = dk.buro_id
    UNION ALL
    SELECT k.ad_soyad, NULL, NULL FROM kullanici k
     WHERE dk.hedef_tur = 'kullanici' AND k.id = dk.hedef_id AND k.buro_id = dk.buro_id
    UNION ALL
    SELECT 'Oturum · ' || k.ad_soyad, NULL, NULL FROM oturum o JOIN kullanici k ON k.id = o.kullanici_id
     WHERE dk.hedef_tur = 'oturum' AND o.id = dk.hedef_id AND k.buro_id = dk.buro_id
    UNION ALL
    SELECT m.ad_unvan, NULL, NULL FROM muvekkil m
     WHERE dk.hedef_tur = 'muvekkil' AND m.id = dk.hedef_id AND m.buro_id = dk.buro_id
    UNION ALL
    SELECT b.ad, NULL, NULL FROM buro b WHERE dk.hedef_tur = 'buro' AND b.id = dk.hedef_id AND b.id = dk.buro_id
    LIMIT 1
) h ON true
"""


def _suzgec(buro_id: UUID, *, kullanici_id: UUID | None, eylemler: list[str] | None,
            baslangic: date | None, bitis: date | None, once: int | None) -> tuple[str, dict]:
    kosullar, p = ["dk.buro_id = :b"], {"b": buro_id, "tz": SAAT_DILIMI}
    if kullanici_id is not None:
        kosullar.append("dk.kullanici_id = :k")
        p["k"] = kullanici_id
    if eylemler:
        if not set(eylemler) <= EYLEMLER:
            raise BelgeHatasi(422, "Geçersiz eylem süzgeci.")
        kosullar.append("dk.eylem = ANY(:e)")
        p["e"] = eylemler
    if baslangic is not None:
        kosullar.append("dk.zaman >= (CAST(:bas AS date)::timestamp AT TIME ZONE :tz)")
        p["bas"] = baslangic
    if bitis is not None:
        kosullar.append("dk.zaman < ((CAST(:bit AS date) + 1)::timestamp AT TIME ZONE :tz)")
        p["bit"] = bitis
    if once is not None:
        kosullar.append("dk.id < :once")
        p["once"] = once
    return " AND ".join(kosullar), p


_SECIM = (
    "SELECT dk.id, dk.zaman, dk.eylem, dk.hedef_tur, dk.hedef_id, host(dk.ip_adresi) AS ip_adresi, dk.ayrinti, "
    "dk.kullanici_id, ku.ad_soyad AS kullanici_adi, ku.e_posta AS kullanici_e_posta, "
    "h.ad AS hedef_adi, h.dava_id AS hedef_dava_id, h.belge_id AS hedef_belge_id "
    "FROM denetim_kaydi dk LEFT JOIN kullanici ku ON ku.id = dk.kullanici_id AND ku.buro_id = dk.buro_id "
)


def kayitlari_listele(
    conn: Connection, *, yonetici_id: UUID, ip_adresi: str | None, kullanici_id: UUID | None = None,
    eylemler: list[str] | None = None, baslangic: date | None = None, bitis: date | None = None,
    once: int | None = None, limit: int = 50,
) -> dict:
    buro_id = yonetici_burosu(conn, yonetici_id)
    limit = max(1, min(limit, SAYFA_EN_COK))
    kosul, p = _suzgec(buro_id, kullanici_id=kullanici_id, eylemler=eylemler, baslangic=baslangic, bitis=bitis,
                       once=once)
    # Bir fazlası okunur: sonraki sayfa olup olmadığı anlaşılır
    satirlar = [dict(s) for s in conn.execute(
        text(_SECIM + _HEDEF + f"WHERE {kosul} ORDER BY dk.id DESC LIMIT :lim"), {**p, "lim": limit + 1},
    ).mappings()]
    devam = len(satirlar) > limit
    satirlar = satirlar[:limit]
    # Okuma, sayfa çekilmeden önce yazılırsa kendi kaydı listenin başında görünür; sonra yazılır
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="goruntuleme", hedef_tur="denetim_kaydi",
                hedef_id=None, ip_adresi=ip_adresi)
    return {"kayitlar": satirlar, "sonraki": satirlar[-1]["id"] if devam else None}


def ozet(conn: Connection, *, yonetici_id: UUID) -> dict:
    """Son 24 saat: eylem sayıları, en çok reddedilen kullanıcılar, kilitlenen hesaplar."""
    buro_id = yonetici_burosu(conn, yonetici_id)
    p = {"b": buro_id}
    son = "dk.buro_id = :b AND dk.zaman > now() - interval '24 hours'"
    eylemler = dict(conn.execute(text(f"SELECT eylem, count(*) FROM denetim_kaydi dk WHERE {son} GROUP BY eylem"),
                                 p).all())
    reddedilenler = [dict(s) for s in conn.execute(text(
        "SELECT dk.kullanici_id, ku.ad_soyad, count(*) AS sayi, max(dk.zaman) AS son_zaman "
        f"FROM denetim_kaydi dk LEFT JOIN kullanici ku ON ku.id = dk.kullanici_id WHERE {son} "
        "AND dk.eylem = 'erisim_reddi' GROUP BY dk.kullanici_id, ku.ad_soyad ORDER BY sayi DESC, son_zaman DESC LIMIT 5"
    ), p).mappings()]
    kilitlenenler = [dict(s) for s in conn.execute(text(
        "SELECT DISTINCT ON (dk.hedef_id) dk.hedef_id AS kullanici_id, ku.ad_soyad, dk.zaman "
        f"FROM denetim_kaydi dk JOIN kullanici ku ON ku.id = dk.hedef_id AND ku.buro_id = dk.buro_id WHERE {son} "
        "AND dk.eylem = 'giris_basarisiz' AND (dk.ayrinti->>'hesap_kilitlendi')::boolean "
        "ORDER BY dk.hedef_id, dk.zaman DESC"
    ), p).mappings()]
    return {"eylemler": eylemler, "reddedilen_kullanicilar": reddedilenler, "kilitlenen_hesaplar": kilitlenenler}


CSV_BASLIKLARI = ["Kayıt no", "Zaman", "Kullanıcı", "E-posta", "Eylem", "Hedef türü", "Hedef", "Hedef kimliği",
                  "IP adresi", "Ayrıntı"]


def disa_aktar(
    conn: Connection, *, yonetici_id: UUID, ip_adresi: str | None, kullanici_id: UUID | None = None,
    eylemler: list[str] | None = None, baslangic: date | None = None, bitis: date | None = None,
) -> str:
    buro_id = yonetici_burosu(conn, yonetici_id)
    kosul, p = _suzgec(buro_id, kullanici_id=kullanici_id, eylemler=eylemler, baslangic=baslangic, bitis=bitis,
                       once=None)
    satirlar = conn.execute(
        text(_SECIM.replace("dk.zaman,", "dk.zaman AT TIME ZONE :tz AS zaman,") + _HEDEF
             + f"WHERE {kosul} ORDER BY dk.id DESC LIMIT :lim"),
        {**p, "lim": DISA_AKTARIM_EN_COK + 1},
    ).mappings().all()
    if len(satirlar) > DISA_AKTARIM_EN_COK:
        raise BelgeHatasi(422, f"En fazla {DISA_AKTARIM_EN_COK} kayıt dışa aktarılabilir; tarih aralığını daraltın.")
    cikti = io.StringIO()
    # Excel'in Türkçe karakterleri doğru açması için UTF-8 BOM ve noktalı virgül ayraç
    cikti.write("﻿")
    yazici = csv.writer(cikti, delimiter=";")
    yazici.writerow(CSV_BASLIKLARI)
    for s in satirlar:
        yazici.writerow([
            s["id"], s["zaman"].strftime("%d.%m.%Y %H:%M:%S"), _hucre(s["kullanici_adi"] or ""),
            _hucre(s["kullanici_e_posta"] or ""), s["eylem"], s["hedef_tur"], _hucre(s["hedef_adi"] or ""),
            s["hedef_id"] or "", s["ip_adresi"] or "",
            _hucre(json.dumps(s["ayrinti"], ensure_ascii=False) if s["ayrinti"] is not None else ""),
        ])
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=yonetici_id, eylem="disa_aktarim", hedef_tur="denetim_kaydi",
                hedef_id=None, ip_adresi=ip_adresi,
                ayrinti={"satir": len(satirlar), "suzgec": {
                    "kullanici_id": str(kullanici_id) if kullanici_id else None, "eylemler": eylemler,
                    "baslangic": baslangic.isoformat() if baslangic else None,
                    "bitis": bitis.isoformat() if bitis else None}})
    return cikti.getvalue()


def _hucre(deger: str) -> str:
    """CSV formül enjeksiyonunu önler: = + - @ ile başlayan hücre Excel'de formül olarak çalışmasın."""
    return "'" + deger if deger[:1] in ("=", "+", "-", "@", "\t", "\r") else deger
