"""İşçide çalışan 'analiz' görevi: bir belgenin bulgularını çıkarıp kaynaklarıyla kaydeder.

- Her bulgu 'otomatik' olarak kaydedilir; avukat onaylayana kadar kesin bilgi değildir.
- Her bulgunun bir kaynak alıntısı (belge, sayfa, karakter aralığı) vardır; kaynaksız bulgu yoktur.
- Aynı belge yeniden analiz edilirse, önceki çalıştırmaların henüz incelenmemiş ('otomatik')
  bulguları silinir; avukatın onayladığı ya da reddettiği bulgular korunur ve aynısı
  tekrar eklenmez.
- Özel nitelikli veri içeren belge, avukat onayı yoksa analiz edilmez (API'de de denetlenir;
  burada ikinci kez denetlenir).
"""

import json

from sqlalchemy import Connection, text

from app import ayarlar
from app.analiz.celiski import CeliskiBulgusu, celiskileri_bul, etiket_bul
from app.analiz.cikarim import Bulgu, ad_anahtari, bulgulari_cikar
from app.analiz.modeller import model_olustur

_AY_ADI = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
           "Kasım", "Aralık"]

_PARA = {"TRY": "TL", "USD": "USD", "EUR": "EUR"}


def bulgu_ozeti(tur: str, deger: str) -> str:
    """Bulgunun avukata gösterilecek kısa hali."""
    if tur == "tutar":
        miktar, birim = deger.split()
        tam, kurus = f"{float(miktar):,.2f}".split(".")
        return f"{tam.replace(',', '.')},{kurus} {_PARA.get(birim, birim)}"
    if tur == "tarih":
        parcalar = deger.split("-")
        if len(parcalar) == 3:
            return f"{parcalar[2]}.{parcalar[1]}.{parcalar[0]}"
        if len(parcalar) == 2:
            return f"{_AY_ADI[int(parcalar[1])]} {parcalar[0]}"
    return deger


class AnalizHatasi(Exception):
    """Yeniden denemenin sonucu değiştirmeyeceği analiz hatası (KaliciHata'ya çevrilir)."""


def analiz_uygula(conn: Connection, analiz_id) -> int:
    """Çalıştırmayı işler, kaydedilen bulgu sayısını döndürür."""
    c = conn.execute(
        text(
            "SELECT ac.id, ac.dava_dosyasi_id, ac.belge_id, ac.model_saglayici, ac.model_adi, "
            "b.ozel_nitelikli, b.ozel_nitelik_onay_zamani "
            "FROM analiz_calistirmasi ac JOIN belge b ON b.id = ac.belge_id WHERE ac.id = :a"
        ),
        {"a": analiz_id},
    ).one_or_none()
    if c is None:
        raise AnalizHatasi("Analiz çalıştırması ya da belgesi bulunamadı.")
    if c.ozel_nitelikli and c.ozel_nitelik_onay_zamani is None:
        raise AnalizHatasi("Özel nitelikli veri içeren belge için avukat onayı yok.")
    sayfalar = conn.execute(
        text("SELECT id, sayfa_no, metin FROM belge_sayfa WHERE belge_id = :b ORDER BY sayfa_no"),
        {"b": c.belge_id},
    ).all()
    if not sayfalar:
        raise AnalizHatasi("Belgede metni çıkarılmış sayfa yok.")

    model = model_olustur(f"{c.model_saglayici}:{c.model_adi}")
    sonuc = bulgulari_cikar(model, [s.metin for s in sayfalar])

    # Avukatın incelenmemiş bulgulara seçtiği etiketler, bulgular yeniden oluşturulunca aynı
    # konuma (sayfa + karakter aralığı) geri yazılmak üzere saklanır
    avukat_etiketleri = conn.execute(
        text(
            "SELECT bu.tur, k.belge_sayfa_id, bu.deger->'konum' AS konum, bu.deger->'etiket' AS etiket FROM bulgu bu "
            "JOIN kaynak_alinti k ON k.bulgu_id = bu.id WHERE k.belge_id = :b AND bu.dogrulama_durumu = 'otomatik' "
            "AND bu.deger->>'etiket_kaynak' = 'avukat' AND bu.deger ? 'konum'"
        ),
        {"b": c.belge_id},
    ).all()
    # Önceki çalıştırmaların incelenmemiş bulguları silinir; incelenmişler korunur
    conn.execute(
        text(
            "DELETE FROM bulgu WHERE dogrulama_durumu = 'otomatik' AND analiz_calistirmasi_id <> :a "
            "AND id IN (SELECT bulgu_id FROM kaynak_alinti WHERE belge_id = :b)"
        ),
        {"a": c.id, "b": c.belge_id},
    )
    # Avukatın düzelttiği bulgu, ilk okunan (yanlış) değeriyle de eşleşir: aynı yanlış okuma
    # yeniden analizde yeni bir bulgu olarak geri gelmesin
    incelenmis = {
        (r.tur, ad_anahtari(deger), r.sayfa_no)
        for r in conn.execute(
            text(
                "SELECT bu.tur, bu.deger->>'deger' AS deger, bu.deger->'duzeltme'->>'onceki' AS onceki, s.sayfa_no "
                "FROM bulgu bu JOIN kaynak_alinti k ON k.bulgu_id = bu.id "
                "JOIN belge_sayfa s ON s.id = k.belge_sayfa_id "
                "WHERE k.belge_id = :b AND bu.dogrulama_durumu <> 'otomatik'"
            ),
            {"b": c.belge_id},
        )
        for deger in (r.deger, r.onceki) if deger
    }
    kaydedilen = 0
    for b in sonuc.bulgular:
        # b.sayfa_no, modele verilen listedeki sıradır (1'den başlar)
        sayfa = sayfalar[b.sayfa_no - 1]
        if (b.tur, ad_anahtari(b.deger), sayfa.sayfa_no) in incelenmis:
            continue
        _kaydet(conn, c, b, sayfa)
        kaydedilen += 1
    for e in avukat_etiketleri:
        conn.execute(
            text(
                "UPDATE bulgu bu SET deger = bu.deger || jsonb_build_object('etiket', CAST(:e AS JSONB), "
                "'etiket_kaynak', 'avukat') FROM kaynak_alinti k WHERE k.bulgu_id = bu.id "
                "AND bu.analiz_calistirmasi_id = :a AND k.belge_sayfa_id = :s AND bu.tur = :t "
                "AND bu.deger->'konum' = CAST(:konum AS JSONB)"
            ),
            {"e": json.dumps(e.etiket, ensure_ascii=False), "a": c.id, "s": e.belge_sayfa_id, "t": e.tur,
             "konum": json.dumps(e.konum)},
        )
    conn.execute(
        text("UPDATE analiz_calistirmasi SET durum = 'tamam', bitis = now() WHERE id = :a"), {"a": c.id}
    )
    celiskileri_guncelle(conn, c.dava_dosyasi_id)
    return kaydedilen


def _kaydet(conn: Connection, c, b: Bulgu, sayfa) -> None:
    deger = {"deger": b.deger, "yontem": b.yontem}
    if b.deger_baslangic is not None:
        deger["konum"] = [b.deger_baslangic, b.deger_bitis]
        if b.tur in ("tarih", "tutar"):
            deger["etiket"] = etiket_bul(sayfa.metin, b.deger_baslangic, b.deger_bitis, b.tur)
    bulgu_id = conn.execute(
        text(
            "INSERT INTO bulgu (analiz_calistirmasi_id, dava_dosyasi_id, tur, ozet, deger, guven_seviyesi) "
            "VALUES (:a, :d, :t, :o, CAST(:v AS JSONB), :g) RETURNING id"
        ),
        {
            "a": c.id, "d": c.dava_dosyasi_id, "t": b.tur, "o": bulgu_ozeti(b.tur, b.deger),
            "v": json.dumps(deger, ensure_ascii=False),
            # Kural bulgusu metindeki kalıbın kendisidir; model bulgusu doğrulanmış olsa da yorumdur
            "g": "yuksek" if b.yontem == "kural" else "orta",
        },
    ).scalar_one()
    conn.execute(
        text(
            "INSERT INTO kaynak_alinti (bulgu_id, belge_id, belge_sayfa_id, alinti_metni, karakter_baslangic, "
            "karakter_bitis) VALUES (:bu, :be, :s, :m, :ba, :bi)"
        ),
        {"bu": bulgu_id, "be": c.belge_id, "s": sayfa.id, "m": b.alinti, "ba": b.baslangic, "bi": b.bitis},
    )


def _etiketleri_yenile(conn: Connection, dava_id) -> None:
    satirlar = conn.execute(
        text(
            "SELECT bu.id, bu.tur, bu.deger, s.metin FROM bulgu bu "
            "JOIN kaynak_alinti k ON k.bulgu_id = bu.id JOIN belge_sayfa s ON s.id = k.belge_sayfa_id "
            "WHERE bu.dava_dosyasi_id = :d AND bu.tur IN ('tarih', 'tutar') AND bu.deger ? 'konum' "
            # Avukatın seçtiği etiket (etiketsiz bırakma kararı dahil) otomatik etiketle ezilmez
            "AND coalesce(bu.deger->>'etiket_kaynak', '') <> 'avukat'"
        ),
        {"d": dava_id},
    ).all()
    for s in satirlar:
        bas, bit = s.deger["konum"]
        etiket = etiket_bul(s.metin, bas, bit, s.tur)
        if etiket != s.deger.get("etiket"):
            conn.execute(
                text("UPDATE bulgu SET deger = jsonb_set(deger, '{etiket}', CAST(:e AS JSONB)) WHERE id = :b"),
                {"b": s.id, "e": json.dumps(etiket, ensure_ascii=False)},
            )


def celiskileri_guncelle(conn: Connection, dava_id) -> int:
    """Dosyanın açık çelişkilerini baştan hesaplar; avukatın incelediği çelişkiler korunur.

    Analiz bitince ve avukat bir bulguyu onaylayıp reddedince çağrılır. Açık çelişki sayısını döndürür.
    Etiketler de saklı konumdan yeniden okunur; böylece etiket sözlüğü güncellenince yeniden analiz gerekmez.
    """
    _etiketleri_yenile(conn, dava_id)
    satirlar = conn.execute(
        text(
            "SELECT bu.id, bu.tur, bu.deger->>'deger' AS deger, bu.ozet, bu.deger->>'etiket' AS etiket, "
            "bu.dogrulama_durumu, k.belge_id, be.orijinal_ad AS belge_adi, s.sayfa_no, "
            "(s.metin_kaynagi = 'ocr' AND (s.ocr_guven_skoru IS NULL OR s.ocr_guven_skoru < :esik)) AS ocr_supheli "
            "FROM bulgu bu JOIN kaynak_alinti k ON k.bulgu_id = bu.id JOIN belge be ON be.id = k.belge_id "
            "JOIN belge_sayfa s ON s.id = k.belge_sayfa_id WHERE bu.dava_dosyasi_id = :d"
        ),
        {"d": dava_id, "esik": ayarlar.OCR_UYARI_ESIGI},
    ).mappings().all()
    celiskiler = celiskileri_bul([CeliskiBulgusu(**s) for s in satirlar])

    conn.execute(text("DELETE FROM uyusmazlik WHERE dava_dosyasi_id = :d AND durum = 'acik'"), {"d": dava_id})
    incelenmis = {
        frozenset((r.b1, r.b2))
        for r in conn.execute(
            text("SELECT ilgili_bulgu_1_id AS b1, ilgili_bulgu_2_id AS b2 FROM uyusmazlik WHERE dava_dosyasi_id = :d"),
            {"d": dava_id},
        )
    }
    acik = 0
    for c in celiskiler:
        if frozenset((c.bulgu_1.id, c.bulgu_2.id)) in incelenmis:
            continue
        conn.execute(
            text(
                "INSERT INTO uyusmazlik (dava_dosyasi_id, tur, ilgili_bulgu_1_id, ilgili_bulgu_2_id, aciklama, ciddiyet) "
                "VALUES (:d, :t, :b1, :b2, :a, :c)"
            ),
            {"d": dava_id, "t": c.tur, "b1": c.bulgu_1.id, "b2": c.bulgu_2.id, "a": c.aciklama, "c": c.ciddiyet},
        )
        acik += 1
    return acik
