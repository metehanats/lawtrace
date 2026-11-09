"""Denetim kaydı (denetim_kaydi tablosu). Tüm modüller kaydı buradan yazar."""

import json
from uuid import UUID

from sqlalchemy import Connection, text

# Aynı kullanıcının aynı hedefi bu süre içinde tekrar görüntülemesi tek kayıtta birleştirilir.
# Arayüz, işlenen belge varken listeyi birkaç saniyede bir yeniliyor; her yenileme ayrı kayıt
# olsaydı tablo anlamsız kayıtlarla dolardı. "Kim neye baktı" bilgisi kaybolmaz.
GORUNTULEME_BIRLESTIRME_SN = 300


def denetim_yaz(
    conn: Connection,
    *,
    buro_id: UUID,
    kullanici_id: UUID | None,
    eylem: str,
    hedef_tur: str,
    hedef_id: UUID | None,
    ip_adresi: str | None,
    ayrinti: dict | None = None,
) -> None:
    parametreler = {
        "b": buro_id, "k": kullanici_id, "e": eylem, "t": hedef_tur, "h": hedef_id, "ip": ip_adresi,
        "a": json.dumps(ayrinti, ensure_ascii=False) if ayrinti is not None else None,
    }
    if eylem == "goruntuleme" and kullanici_id is not None:
        conn.execute(
            text(
                "INSERT INTO denetim_kaydi (buro_id, kullanici_id, eylem, hedef_tur, hedef_id, ip_adresi, ayrinti) "
                "SELECT :b, :k, :e, :t, CAST(:h AS UUID), :ip, CAST(:a AS JSONB) "
                "WHERE NOT EXISTS (SELECT 1 FROM denetim_kaydi WHERE buro_id = :b AND kullanici_id = :k "
                "    AND eylem = :e AND hedef_tur = :t AND hedef_id IS NOT DISTINCT FROM CAST(:h AS UUID) "
                "    AND zaman > now() - make_interval(secs => :sn))"
            ),
            {**parametreler, "sn": GORUNTULEME_BIRLESTIRME_SN},
        )
        return
    conn.execute(
        text(
            "INSERT INTO denetim_kaydi (buro_id, kullanici_id, eylem, hedef_tur, hedef_id, ip_adresi, ayrinti) "
            "VALUES (:b, :k, :e, :t, :h, :ip, CAST(:a AS JSONB))"
        ),
        parametreler,
    )
