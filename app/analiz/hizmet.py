"""Analiz ve bulgu işlemleri (API'nin kullandığı servis katmanı).

Kurallar:
- Analiz büro düzeyinde açılır (buro.analiz_modeli); kapalıysa başlatılamaz.
- Analizi başlatma, bulgu onaylama/reddetme ve özel nitelik onayı: yönetici ve avukat.
  Stajyer bulguları görür ama karar veremez (nihai sorumluluk avukattadır).
- Özel nitelikli işaretli belge, avukat onayı olmadan analize gönderilmez.
- Her başlatma, onay, ret ve işaret değişikliği denetim kaydına yazılır.
"""

import json
from dataclasses import asdict
from uuid import UUID

from sqlalchemy import Connection, text

from app.analiz import iddia, zaman
from app.analiz.celiski import TEK_DEGERLI_ETIKETLER, yazim_anahtari
from app.analiz.cikarim import ISTEM_SURUMU, ad_normalle, tarih_normalle, tr_kucuk, tutar_normalle
from app.analiz.gorev import bulgu_ozeti, celiskileri_guncelle
from app.belge.erisim import BelgeHatasi, ErisimReddi, belge_erisimini_denetle, dava_erisimini_denetle
from app.dava.hizmet import OLUSTURABILEN_ROLLER, kullanici_al
from app.denetim import denetim_yaz

KARARLAR = {"onay": ("onaylandi", "onay"), "red": ("reddedildi", "reddetme")}


def _karar_verebilir(kullanici) -> None:
    if kullanici.rol not in OLUSTURABILEN_ROLLER:
        raise ErisimReddi(403, "Bu işlemi yalnızca avukat ya da büro yöneticisi yapabilir.", "yetki_yok")


def _buro_modeli(conn: Connection, buro_id: UUID) -> str | None:
    return conn.execute(text("SELECT analiz_modeli FROM buro WHERE id = :b"), {"b": buro_id}).scalar_one()


def analiz_baslat(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, belge_idleri: list[UUID] | None, ip_adresi: str | None
) -> dict:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id, yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    model = _buro_modeli(conn, buro_id)
    if not model:
        raise BelgeHatasi(409, "Analiz bu büro için kapalı. Büro yöneticisi açabilir.")
    saglayici, _, model_adi = model.partition(":")

    belgeler = conn.execute(
        text(
            "SELECT b.id, b.orijinal_ad, b.durum, b.ozel_nitelikli, b.ozel_nitelik_onay_zamani, "
            "EXISTS (SELECT 1 FROM isleme_gorevi g WHERE g.belge_id = b.id AND g.adim = 'analiz' "
            "        AND g.durum IN ('bekliyor', 'calisiyor')) AS sirada "
            "FROM belge b WHERE b.dava_dosyasi_id = :d "
            "AND (CAST(:idler AS UUID[]) IS NULL OR b.id = ANY(CAST(:idler AS UUID[]))) ORDER BY b.yuklenme"
        ),
        {"d": dava_id, "idler": [str(i) for i in belge_idleri] if belge_idleri else None},
    ).all()

    baslatilan, onay_bekleyen, atlanan = [], [], []
    for b in belgeler:
        if b.durum != "hazir":
            atlanan.append({"belge_id": b.id, "orijinal_ad": b.orijinal_ad, "neden": "metni henüz hazır değil"})
        elif b.sirada:
            atlanan.append({"belge_id": b.id, "orijinal_ad": b.orijinal_ad, "neden": "zaten analiz sırasında"})
        elif b.ozel_nitelikli and b.ozel_nitelik_onay_zamani is None:
            onay_bekleyen.append({"belge_id": b.id, "orijinal_ad": b.orijinal_ad})
        else:
            analiz_id = conn.execute(
                text(
                    "INSERT INTO analiz_calistirmasi (buro_id, dava_dosyasi_id, kapsam, belge_id, model_saglayici, "
                    "model_adi, prompt_surumu, calistiran_kullanici_id) "
                    "VALUES (:b, :d, 'tek_belge', :be, :s, :m, :p, :k) RETURNING id"
                ),
                {"b": buro_id, "d": dava_id, "be": b.id, "s": saglayici, "m": model_adi, "p": ISTEM_SURUMU,
                 "k": kullanici_id},
            ).scalar_one()
            conn.execute(
                text("INSERT INTO isleme_gorevi (belge_id, adim, analiz_calistirmasi_id) VALUES (:b, 'analiz', :a)"),
                {"b": b.id, "a": analiz_id},
            )
            baslatilan.append({"belge_id": b.id, "orijinal_ad": b.orijinal_ad, "analiz_id": analiz_id})
    if baslatilan:
        denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="analiz", hedef_tur="dava_dosyasi",
                    hedef_id=dava_id, ip_adresi=ip_adresi,
                    ayrinti={"model": model, "belgeler": [str(x["belge_id"]) for x in baslatilan]})
    return {"baslatilan": baslatilan, "onay_bekleyen": onay_bekleyen, "atlanan": atlanan}


def _dosya_kapali(conn: Connection, dava_id: UUID) -> bool:
    return conn.execute(text("SELECT durum = 'kapali' FROM dava_dosyasi WHERE id = :d"), {"d": dava_id}).scalar_one()


def analiz_durumu(conn: Connection, *, dava_id: UUID, kullanici_id: UUID) -> dict:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    kullanici = kullanici_al(conn, kullanici_id)
    belgeler = conn.execute(
        text(
            "SELECT b.id AS belge_id, b.orijinal_ad, b.durum AS belge_durumu, b.ozel_nitelikli, "
            "b.ozel_nitelik_nedeni, b.ozel_nitelik_onay_zamani IS NOT NULL AS ozel_nitelik_onayli, "
            "son.durum AS analiz_durumu, son.baslangic AS analiz_baslangic, son.bitis AS analiz_bitis, "
            "son.gorev_hatasi AS analiz_hatasi, "
            "(SELECT count(DISTINCT k.bulgu_id) FROM kaynak_alinti k WHERE k.belge_id = b.id) AS bulgu_sayisi "
            "FROM belge b LEFT JOIN LATERAL ("
            "  SELECT ac.durum, ac.baslangic, ac.bitis, g.hata_mesaji AS gorev_hatasi "
            "  FROM analiz_calistirmasi ac LEFT JOIN isleme_gorevi g ON g.analiz_calistirmasi_id = ac.id "
            "  WHERE ac.belge_id = b.id ORDER BY ac.baslangic DESC LIMIT 1"
            ") son ON true WHERE b.dava_dosyasi_id = :d ORDER BY b.yuklenme"
        ),
        {"d": dava_id},
    ).mappings().all()
    return {
        "analiz_acik": _buro_modeli(conn, buro_id) is not None,
        "model": _buro_modeli(conn, buro_id),
        # Kapalı dosyada kimse karar veremez (salt okunur); arayüz düğmeleri buna göre gizler
        "karar_verebilir": kullanici.rol in OLUSTURABILEN_ROLLER and not _dosya_kapali(conn, dava_id),
        "belgeler": [dict(b) for b in belgeler],
    }


def ozel_nitelik_onayla(conn: Connection, *, belge_id: UUID, kullanici_id: UUID, ip_adresi: str | None) -> None:
    belge = belge_erisimini_denetle(conn, belge_id, kullanici_id, yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    guncellenen = conn.execute(
        text(
            "UPDATE belge SET ozel_nitelik_onay_kullanici_id = :k, ozel_nitelik_onay_zamani = now() "
            "WHERE id = :b AND ozel_nitelikli AND ozel_nitelik_onay_zamani IS NULL"
        ),
        {"b": belge_id, "k": kullanici_id},
    ).rowcount
    if guncellenen:
        denetim_yaz(conn, buro_id=belge.buro_id, kullanici_id=kullanici_id, eylem="onay", hedef_tur="belge",
                    hedef_id=belge_id, ip_adresi=ip_adresi, ayrinti={"konu": "ozel_nitelikli_veri_analizi"})


def ozel_nitelik_isaretle(
    conn: Connection, *, belge_id: UUID, kullanici_id: UUID, isaretli: bool, neden: str | None, ip_adresi: str | None
) -> None:
    """Avukatın elle işaretlemesi. İşaret kaldırılırsa verilmiş onay da düşer."""
    belge = belge_erisimini_denetle(conn, belge_id, kullanici_id, yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    conn.execute(
        text(
            "UPDATE belge SET ozel_nitelikli = :i, ozel_nitelik_nedeni = :n, "
            "ozel_nitelik_onay_kullanici_id = NULL, ozel_nitelik_onay_zamani = NULL WHERE id = :b"
        ),
        {"b": belge_id, "i": isaretli, "n": (neden or "Avukat tarafından işaretlendi") if isaretli else None},
    )
    denetim_yaz(conn, buro_id=belge.buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="belge",
                hedef_id=belge_id, ip_adresi=ip_adresi, ayrinti={"ozel_nitelikli": isaretli})


def bulgulari_listele(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, ip_adresi: str | None
) -> list[dict]:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    satirlar = conn.execute(
        text(
            "SELECT bu.id, bu.tur, bu.ozet, bu.deger->>'deger' AS deger, bu.deger->>'yontem' AS yontem, "
            "bu.deger->>'etiket' AS etiket, bu.deger->>'etiket_kaynak' AS etiket_kaynak, "
            "bu.deger->'duzeltme'->>'onceki_ozet' AS duzeltme_onceki, "
            "bu.guven_seviyesi, bu.dogrulama_durumu, bu.olusturma, "
            "k.belge_id, be.orijinal_ad AS belge_adi, s.sayfa_no, s.metin_kaynagi, s.ocr_guven_skoru, "
            "k.alinti_metni, k.karakter_baslangic, k.karakter_bitis, "
            "son_inc.karar AS son_karar, son_inc.notu AS son_not, son_inc.ad_soyad AS inceleyen "
            "FROM bulgu bu JOIN kaynak_alinti k ON k.bulgu_id = bu.id "
            "JOIN belge be ON be.id = k.belge_id JOIN belge_sayfa s ON s.id = k.belge_sayfa_id "
            "LEFT JOIN LATERAL (SELECT i.karar, i.notu, ku.ad_soyad FROM bulgu_inceleme i "
            "  JOIN kullanici ku ON ku.id = i.kullanici_id WHERE i.bulgu_id = bu.id ORDER BY i.tarih DESC LIMIT 1"
            ") son_inc ON true "
            "WHERE bu.dava_dosyasi_id = :d "
            "ORDER BY array_position(ARRAY['tarih','tutar','kisi','kurum'], bu.tur), bu.deger->>'deger', "
            "be.orijinal_ad, s.sayfa_no"
        ),
        {"d": dava_id},
    ).mappings().all()
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="goruntuleme", hedef_tur="bulgu_listesi",
                hedef_id=dava_id, ip_adresi=ip_adresi)
    return [{**s, "grup_anahtari": grup_anahtari(s["tur"], s["deger"])} for s in satirlar]


def grup_anahtari(tur: str, deger: str) -> str:
    """Aynı değerin farklı kaynaklardaki bulguları bu anahtarla tek satırda toplanır.

    Tarih ve tutar normalize değerleriyle; adlar büyük/küçük harf, unvan ve noktalama farkı
    yok sayılarak gruplanır. Harf farkı olan yazılışlar ("Güneş" / "Gunes") ayrı kalır;
    onları çelişki tespiti "farklı yazılmış olabilir" diye işaretler.
    """
    if tur in ("kisi", "kurum"):
        return f"{tur}:{yazim_anahtari(deger)}"
    return f"{tur}:{deger}"


def zaman_cizelgesi(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, ip_adresi: str | None
) -> list[dict]:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    bulgular = [
        zaman.TarihBulgusu(**s) for s in conn.execute(
            text(
                "SELECT bu.id, bu.deger->>'deger' AS deger, bu.ozet, bu.deger->>'etiket' AS etiket, "
                "k.belge_id, be.orijinal_ad AS belge_adi, s.sayfa_no, k.alinti_metni AS alinti, "
                "k.karakter_baslangic AS bas, k.karakter_bitis AS bit, bu.dogrulama_durumu "
                "FROM bulgu bu JOIN kaynak_alinti k ON k.bulgu_id = bu.id "
                "JOIN belge be ON be.id = k.belge_id JOIN belge_sayfa s ON s.id = k.belge_sayfa_id "
                "WHERE bu.dava_dosyasi_id = :d AND bu.tur = 'tarih'"
            ),
            {"d": dava_id},
        ).mappings()
    ]
    celiskili = {}
    for s in conn.execute(
        text("SELECT ilgili_bulgu_1_id, ilgili_bulgu_2_id, aciklama FROM uyusmazlik "
             "WHERE dava_dosyasi_id = :d AND tur = 'tarih' AND durum = 'acik'"),
        {"d": dava_id},
    ):
        celiskili[s.ilgili_bulgu_1_id] = celiskili[s.ilgili_bulgu_2_id] = s.aciklama
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="goruntuleme", hedef_tur="zaman_cizelgesi",
                hedef_id=dava_id, ip_adresi=ip_adresi)
    return [asdict(o) for o in zaman.zaman_cizelgesi(bulgular, celiskili)]


def iddia_haritasi(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, ip_adresi: str | None
) -> list[dict]:
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    belgeler = conn.execute(
        text("SELECT id, orijinal_ad, ozel_nitelikli AND ozel_nitelik_onay_zamani IS NULL AS kapali "
             "FROM belge WHERE dava_dosyasi_id = :d AND durum = 'hazir' ORDER BY orijinal_ad"),
        {"d": dava_id},
    ).all()
    # Onaysız özel nitelikli belgenin metni okunmaz (analizdeki kuralın aynısı); yalnızca adı kullanılır
    sayfalar: dict = {}
    acik_idler = [b.id for b in belgeler if not b.kapali]
    if acik_idler:
        for s in conn.execute(
            text("SELECT belge_id, sayfa_no, metin FROM belge_sayfa WHERE belge_id = ANY(:b) ORDER BY sayfa_no"),
            {"b": acik_idler},
        ):
            sayfalar.setdefault(s.belge_id, []).append(iddia.Sayfa(s.sayfa_no, s.metin))
    bulgular = [
        iddia.DegerBulgusu(**s) for s in conn.execute(
            text(
                "SELECT bu.id, k.belge_id, s.sayfa_no, bu.tur, bu.deger->>'deger' AS deger, bu.ozet, "
                "(bu.deger->'konum'->>0)::int AS bas, (bu.deger->'konum'->>1)::int AS bit, "
                "k.alinti_metni AS alinti, k.karakter_baslangic AS alinti_bas, k.karakter_bitis AS alinti_bit, "
                "bu.dogrulama_durumu "
                "FROM bulgu bu JOIN kaynak_alinti k ON k.bulgu_id = bu.id JOIN belge_sayfa s ON s.id = k.belge_sayfa_id "
                "WHERE bu.dava_dosyasi_id = :d AND bu.tur IN ('tarih', 'tutar') AND bu.deger ? 'konum'"
            ),
            {"d": dava_id},
        ).mappings()
    ]
    celiskiler: dict = {}
    for s in conn.execute(
        text("SELECT ilgili_bulgu_1_id AS a, ilgili_bulgu_2_id AS b, aciklama FROM uyusmazlik "
             "WHERE dava_dosyasi_id = :d AND tur IN ('tarih', 'tutar') AND durum = 'acik'"),
        {"d": dava_id},
    ):
        celiskiler.setdefault(s.a, []).append((s.aciklama, s.b))
        celiskiler.setdefault(s.b, []).append((s.aciklama, s.a))
    haritalar = iddia.harita_olustur(
        [iddia.DosyaBelgesi(b.id, b.orijinal_ad, sayfalar.get(b.id, [])) for b in belgeler], bulgular, celiskiler)
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="goruntuleme", hedef_tur="iddia_haritasi",
                hedef_id=dava_id, ip_adresi=ip_adresi)
    return [
        {**asdict(h), "iddialar": [{**asdict(i), "dayanaksiz": i.dayanaksiz} for i in h.iddialar]}
        for h in haritalar
    ]


CELISKI_DURUMLARI = {"acik", "incelendi", "cozuldu"}


def celiskileri_listele(conn: Connection, *, dava_id: UUID, kullanici_id: UUID) -> list[dict]:
    dava_erisimini_denetle(conn, dava_id, kullanici_id)
    satirlar = conn.execute(
        text(
            "SELECT u.id, u.tur, u.aciklama, u.ciddiyet, u.durum, "
            "b1.id AS b1_id, b1.ozet AS b1_ozet, b1.dogrulama_durumu AS b1_durum, "
            "k1.belge_id AS b1_belge_id, e1.orijinal_ad AS b1_belge_adi, s1.sayfa_no AS b1_sayfa_no, "
            "k1.alinti_metni AS b1_alinti, k1.karakter_baslangic AS b1_bas, k1.karakter_bitis AS b1_bit, "
            "b2.id AS b2_id, b2.ozet AS b2_ozet, b2.dogrulama_durumu AS b2_durum, "
            "k2.belge_id AS b2_belge_id, e2.orijinal_ad AS b2_belge_adi, s2.sayfa_no AS b2_sayfa_no, "
            "k2.alinti_metni AS b2_alinti, k2.karakter_baslangic AS b2_bas, k2.karakter_bitis AS b2_bit "
            "FROM uyusmazlik u "
            "JOIN bulgu b1 ON b1.id = u.ilgili_bulgu_1_id JOIN kaynak_alinti k1 ON k1.bulgu_id = b1.id "
            "JOIN belge e1 ON e1.id = k1.belge_id JOIN belge_sayfa s1 ON s1.id = k1.belge_sayfa_id "
            "JOIN bulgu b2 ON b2.id = u.ilgili_bulgu_2_id JOIN kaynak_alinti k2 ON k2.bulgu_id = b2.id "
            "JOIN belge e2 ON e2.id = k2.belge_id JOIN belge_sayfa s2 ON s2.id = k2.belge_sayfa_id "
            "WHERE u.dava_dosyasi_id = :d "
            "ORDER BY u.durum = 'acik' DESC, array_position(ARRAY['yuksek','orta','dusuk'], u.ciddiyet), u.aciklama"
        ),
        {"d": dava_id},
    ).mappings().all()

    def taraf(s, on):
        return {k[len(on):]: s[k] for k in s.keys() if k.startswith(on)}

    return [
        {"id": s["id"], "tur": s["tur"], "aciklama": s["aciklama"], "ciddiyet": s["ciddiyet"], "durum": s["durum"],
         "bulgu_1": taraf(s, "b1_"), "bulgu_2": taraf(s, "b2_")}
        for s in satirlar
    ]


def celiski_durumu_degistir(
    conn: Connection, *, celiski_id: UUID, kullanici_id: UUID, durum: str, ip_adresi: str | None
) -> None:
    if durum not in CELISKI_DURUMLARI:
        raise BelgeHatasi(422, "Geçersiz durum.")
    dava_id = conn.execute(
        text("SELECT dava_dosyasi_id FROM uyusmazlik WHERE id = :u"), {"u": celiski_id}
    ).scalar_one_or_none()
    if dava_id is None:
        raise ErisimReddi(404, "Çelişki bulunamadı.", "bulunamadi")
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id, bulunamadi="Çelişki bulunamadı.", yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    conn.execute(text("UPDATE uyusmazlik SET durum = :d WHERE id = :u"), {"u": celiski_id, "d": durum})
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="uyusmazlik",
                hedef_id=celiski_id, ip_adresi=ip_adresi, ayrinti={"durum": durum})


def deger_ayristir(tur: str, girilen: str, onceki: str) -> str:
    """Avukatın yazdığı düzeltmeyi bulgunun saklama biçimine çevirir; anlaşılamazsa BelgeHatasi."""
    metin = " ".join(girilen.split())
    if not metin:
        raise BelgeHatasi(422, "Doğru değeri yazın.")
    if tur == "tarih":
        deger = tarih_normalle(metin)
        if deger is None:
            raise BelgeHatasi(422, "Tarih anlaşılamadı. Örnek: 17.03.2025 ya da 17 Mart 2025.")
        return deger
    if tur == "tutar":
        # Para birimi yazılmadıysa bulgunun kendi birimi kullanılır ("368.420,50" → TL)
        deger = tutar_normalle(metin) or tutar_normalle(f"{metin} {onceki.split()[-1]}")
        if deger is None:
            raise BelgeHatasi(422, "Tutar anlaşılamadı. Örnek: 386.420,50 TL.")
        return deger
    ad = ad_normalle(metin)
    if len(ad) < 2:
        raise BelgeHatasi(422, "Ad çok kısa.")
    return ad


def bulgu_duzelt(
    conn: Connection, *, bulgu_id: UUID, kullanici_id: UUID, deger: str, notu: str | None, ip_adresi: str | None
) -> dict:
    """Avukat yanlış okunan değeri düzeltir. Kaynak (belge, sayfa, alıntı) aynı kalır: avukat
    "bu kaynakta yazan değer budur" der. Bulgu onaylanmış sayılır; eski değer ve düzelten kayıtta durur.
    Düzeltilen bulgu yeniden analizde korunur (incelenmiş bulgulara dokunulmaz)."""
    bulgu = conn.execute(
        text("SELECT id, dava_dosyasi_id, tur, ozet, deger FROM bulgu WHERE id = :b FOR UPDATE"), {"b": bulgu_id}
    ).one_or_none()
    if bulgu is None:
        raise ErisimReddi(404, "Bulgu bulunamadı.", "bulunamadi")
    buro_id = dava_erisimini_denetle(conn, bulgu.dava_dosyasi_id, kullanici_id, bulunamadi="Bulgu bulunamadı.",
                                     yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    onceki = bulgu.deger["deger"]
    yeni = deger_ayristir(bulgu.tur, deger, onceki)
    if yeni == onceki:
        raise BelgeHatasi(422, "Yazdığınız değer bulgudakiyle aynı; düzeltme yerine onaylayın.")
    yeni_ozet = bulgu_ozeti(bulgu.tur, yeni)
    duzeltme = {"onceki": onceki, "onceki_ozet": bulgu.ozet, "kullanici_id": str(kullanici_id)}
    conn.execute(
        text("UPDATE bulgu SET deger = jsonb_set(jsonb_set(deger, '{deger}', to_jsonb(CAST(:y AS TEXT))), "
             "'{duzeltme}', CAST(:d AS JSONB)), ozet = :o, dogrulama_durumu = 'onaylandi' WHERE id = :b"),
        {"b": bulgu_id, "y": yeni, "o": yeni_ozet, "d": json.dumps(duzeltme, ensure_ascii=False)},
    )
    conn.execute(
        text("INSERT INTO bulgu_inceleme (bulgu_id, kullanici_id, karar, notu) VALUES (:b, :k, 'duzeltme', :n)"),
        {"b": bulgu_id, "k": kullanici_id, "n": (notu or "").strip() or f"Önceki değer: {bulgu.ozet}"},
    )
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="bulgu",
                hedef_id=bulgu_id, ip_adresi=ip_adresi,
                ayrinti={"islem": "duzeltme", "onceki": bulgu.ozet, "yeni": yeni_ozet})
    # Değer değişti: çelişkiler (ör. iki belgede farklı dava değeri) yeniden hesaplanır
    celiskileri_guncelle(conn, bulgu.dava_dosyasi_id)
    return {"id": bulgu_id, "ozet": yeni_ozet, "dogrulama_durumu": "onaylandi"}


def etiket_secenekleri() -> dict[str, list[str]]:
    """Avukatın seçebileceği hazır etiketler (çelişki tespitinin tanıdıkları); serbest etiket de girilebilir."""
    return {tur: [ad for ad, _ in liste] for tur, liste in TEK_DEGERLI_ETIKETLER.items()}


def bulgu_etiketle(
    conn: Connection, *, bulgu_id: UUID, kullanici_id: UUID, etiket: str | None, ip_adresi: str | None
) -> dict:
    """Avukat tarih/tutar bulgusunun etiketini seçer (ör. "dava değeri", "hasar bedeli") ya da
    etiketsiz bırakır (None). Seçim otomatik etiketle ezilmez, yeniden analizde korunur; çelişki
    tespiti bu etiketi kullanır. Bulgunun doğrulama durumu değişmez (etiket bir karar değildir)."""
    bulgu = conn.execute(
        text("SELECT id, dava_dosyasi_id, tur, deger FROM bulgu WHERE id = :b FOR UPDATE"), {"b": bulgu_id}
    ).one_or_none()
    if bulgu is None:
        raise ErisimReddi(404, "Bulgu bulunamadı.", "bulunamadi")
    buro_id = dava_erisimini_denetle(conn, bulgu.dava_dosyasi_id, kullanici_id, bulunamadi="Bulgu bulunamadı.",
                                     yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    if bulgu.tur not in ("tarih", "tutar"):
        raise BelgeHatasi(422, "Etiket yalnızca tarih ve tutar bulgularına verilir.")
    if etiket is not None:
        # Aynı etiket farklı yazılırsa ("Hasar Bedeli" / "hasar  bedeli") çelişki eşleşmesi kaçmasın
        etiket = tr_kucuk(" ".join(etiket.split()))
        if not 2 <= len(etiket) <= 40:
            raise BelgeHatasi(422, "Etiket 2–40 karakter olmalı.")
    onceki = bulgu.deger.get("etiket")
    conn.execute(
        text("UPDATE bulgu SET deger = deger || jsonb_build_object('etiket', CAST(:e AS JSONB), "
             "'etiket_kaynak', 'avukat') WHERE id = :b"),
        {"b": bulgu_id, "e": json.dumps(etiket, ensure_ascii=False)},
    )
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="bulgu",
                hedef_id=bulgu_id, ip_adresi=ip_adresi, ayrinti={"islem": "etiket", "onceki": onceki, "yeni": etiket})
    celiskileri_guncelle(conn, bulgu.dava_dosyasi_id)
    return {"id": bulgu_id, "etiket": etiket}


def bulgu_incele(
    conn: Connection, *, bulgu_id: UUID, kullanici_id: UUID, karar: str, notu: str | None, ip_adresi: str | None
) -> dict:
    if karar not in KARARLAR:
        raise BelgeHatasi(422, "Geçersiz karar.")
    bulgu = conn.execute(
        text("SELECT id, dava_dosyasi_id FROM bulgu WHERE id = :b"), {"b": bulgu_id}
    ).one_or_none()
    if bulgu is None:
        raise ErisimReddi(404, "Bulgu bulunamadı.", "bulunamadi")
    buro_id = dava_erisimini_denetle(conn, bulgu.dava_dosyasi_id, kullanici_id, bulunamadi="Bulgu bulunamadı.",
                                     yazma=True)
    _karar_verebilir(kullanici_al(conn, kullanici_id))
    durum, eylem = KARARLAR[karar]
    conn.execute(
        text("INSERT INTO bulgu_inceleme (bulgu_id, kullanici_id, karar, notu) VALUES (:b, :k, :c, :n)"),
        {"b": bulgu_id, "k": kullanici_id, "c": karar, "n": (notu or "").strip() or None},
    )
    conn.execute(text("UPDATE bulgu SET dogrulama_durumu = :d WHERE id = :b"), {"b": bulgu_id, "d": durum})
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem=eylem, hedef_tur="bulgu",
                hedef_id=bulgu_id, ip_adresi=ip_adresi)
    # Reddedilen bulgu çelişki hesabından çıkar; çelişkiler yeniden hesaplanır
    celiskileri_guncelle(conn, bulgu.dava_dosyasi_id)
    return {"id": bulgu_id, "dogrulama_durumu": durum}
