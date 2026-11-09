"""Müvekkil ve dava dosyası oluşturma ve düzenleme, dosya erişimi yönetimi.

Yetki kuralları:
- Müvekkil ve dava oluşturma, müvekkil düzenleme: yönetici ve avukat. Stajyer oluşturamaz, düzenleyemez.
- Müvekkilleri görme: yönetici ve avukat bürodaki tüm müvekkilleri görür (çıkar çatışması
  kontrolü için); stajyer yalnızca erişimi olan dosyaların müvekkillerini görür.
- Dava dosyasını düzenleme ve kapatma: büro yöneticisi ya da o dosyanın sorumlusu (stajyer değil).
  Kapalı dosya salt okunurdur (bkz. app/belge/erisim.py); yalnızca yeniden açılabilir.
- Dosya erişimini yönetme: büro yöneticisi ya da o dosyada "sorumlu" olan kullanıcı.
  Dosyanın son sorumlusu kaldırılamaz ya da "inceleyen"e düşürülemez.

Müvekkil kimlik numarası ve iletişim bilgileri app/kripto.py ile şifrelenerek saklanır.
"""

import json
from uuid import UUID, uuid4

from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError

from app import kripto
from app.belge.erisim import DOSYA_KAPALI, BelgeHatasi, ErisimReddi, dava_erisimini_denetle
from app.denetim import denetim_yaz

OLUSTURABILEN_ROLLER = {"yonetici", "avukat"}
ERISIM_ROLLERI = {"sorumlu", "inceleyen"}


def kullanici_al(conn: Connection, kullanici_id: UUID):
    return conn.execute(
        text("SELECT id, buro_id, rol, ad_soyad FROM kullanici WHERE id = :k AND aktif"), {"k": kullanici_id}
    ).one()


def _olusturabilir_mi(kullanici) -> None:
    if kullanici.rol not in OLUSTURABILEN_ROLLER:
        raise ErisimReddi(403, "Bu işlem için yetkiniz yok.", "yetki_yok")


# --- Kimlik numarası doğrulama --------------------------------------------

def tckn_gecerli(no: str) -> bool:
    if len(no) != 11 or not no.isdigit() or no[0] == "0":
        return False
    h = [int(c) for c in no]
    onuncu = ((h[0] + h[2] + h[4] + h[6] + h[8]) * 7 - (h[1] + h[3] + h[5] + h[7])) % 10
    return onuncu == h[9] and sum(h[:10]) % 10 == h[10]


def _kimlik_no_dogrula(tur: str, kimlik_no: str) -> str:
    no = kimlik_no.replace(" ", "")
    if tur == "gercek_kisi" and not tckn_gecerli(no):
        raise BelgeHatasi(422, "T.C. kimlik numarası geçersiz.")
    # Vergi kimlik numarasında yalnızca biçim denetlenir (10 hane)
    if tur == "tuzel_kisi" and not (len(no) == 10 and no.isdigit()):
        raise BelgeHatasi(422, "Vergi kimlik numarası 10 haneli olmalı.")
    return no


def maskele(no: str) -> str:
    return "•" * (len(no) - 2) + no[-2:]


# --- Müvekkil -------------------------------------------------------------

def _sifreli_alanlar(
    conn: Connection, *, buro_id: UUID, muvekkil_id: UUID, tur: str, kimlik_no: str | None,
    iletisim: dict[str, str | None],
) -> tuple[bytes | None, str | None, bytes | None]:
    """Kimlik numarasını doğrular, mükerrer kaydı denetler; kimlik ve iletişimi şifreler."""
    kimlik_sifreli = kimlik_ozet = None
    if kimlik_no and kimlik_no.strip():
        no = _kimlik_no_dogrula(tur, kimlik_no)
        kimlik_sifreli = kripto.sifrele(no, kayit_id=muvekkil_id, alan="kimlik_no")
        kimlik_ozet = kripto.arama_ozeti(no, alan="kimlik_no")
        mevcut = conn.execute(
            text("SELECT id, ad_unvan FROM muvekkil WHERE buro_id = :b AND kimlik_no_ozet = :o AND id <> :m"),
            {"b": buro_id, "o": kimlik_ozet, "m": muvekkil_id},
        ).one_or_none()
        if mevcut:
            raise BelgeHatasi(409, f"Bu kimlik numarasıyla kayıtlı müvekkil var: {mevcut.ad_unvan}.")
    iletisim = _iletisim_temizle(iletisim)
    iletisim_sifreli = (
        kripto.sifrele(json.dumps(iletisim, ensure_ascii=False), kayit_id=muvekkil_id, alan="iletisim")
        if iletisim else None
    )
    return kimlik_sifreli, kimlik_ozet, iletisim_sifreli


def _iletisim_temizle(iletisim: dict[str, str | None]) -> dict[str, str]:
    return {k: v.strip() for k, v in iletisim.items() if v and v.strip()}


def muvekkil_olustur(
    conn: Connection,
    *,
    kullanici_id: UUID,
    tur: str,
    ad_unvan: str,
    kimlik_no: str | None,
    iletisim: dict[str, str],
    ip_adresi: str | None,
) -> dict:
    kullanici = kullanici_al(conn, kullanici_id)
    _olusturabilir_mi(kullanici)
    ad_unvan = ad_unvan.strip()
    if not ad_unvan:
        raise BelgeHatasi(422, "Ad / unvan boş olamaz.")
    muvekkil_id = uuid4()
    kimlik_sifreli, kimlik_ozet, iletisim_sifreli = _sifreli_alanlar(
        conn, buro_id=kullanici.buro_id, muvekkil_id=muvekkil_id, tur=tur, kimlik_no=kimlik_no, iletisim=iletisim)
    try:
        with conn.begin_nested():
            conn.execute(
                text(
                    "INSERT INTO muvekkil (id, buro_id, tur, ad_unvan, kimlik_no_sifreli, iletisim_sifreli, "
                    "kimlik_no_ozet, olusturan_kullanici_id) VALUES (:id, :b, :t, :a, :ks, :is, :ko, :k)"
                ),
                {"id": muvekkil_id, "b": kullanici.buro_id, "t": tur, "a": ad_unvan, "ks": kimlik_sifreli,
                 "is": iletisim_sifreli, "ko": kimlik_ozet, "k": kullanici_id},
            )
    except IntegrityError:
        # Eşzamanlı aynı kayıt
        raise BelgeHatasi(409, "Bu kimlik numarasıyla kayıtlı müvekkil var.")
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="olusturma",
                hedef_tur="muvekkil", hedef_id=muvekkil_id, ip_adresi=ip_adresi)
    return {"id": muvekkil_id}


def muvekkil_guncelle(
    conn: Connection,
    *,
    kullanici_id: UUID,
    muvekkil_id: UUID,
    tur: str,
    ad_unvan: str,
    kimlik_no: str | None,
    iletisim: dict[str, str | None],
    ip_adresi: str | None,
) -> None:
    """Müvekkilin tüm alanlarını gelen değerlerle değiştirir (boş alan silinir).

    Denetime yalnızca değişen alanların adları yazılır; kimlik ve iletişim değerleri yazılmaz.
    """
    kullanici = kullanici_al(conn, kullanici_id)
    _olusturabilir_mi(kullanici)
    eski = conn.execute(
        text("SELECT id, tur, ad_unvan, kimlik_no_sifreli, iletisim_sifreli FROM muvekkil "
             "WHERE id = :m AND buro_id = :b FOR UPDATE"),
        {"m": muvekkil_id, "b": kullanici.buro_id},
    ).one_or_none()
    if eski is None:
        raise ErisimReddi(404, "Müvekkil bulunamadı.", "bulunamadi")
    ad_unvan = ad_unvan.strip()
    if not ad_unvan:
        raise BelgeHatasi(422, "Ad / unvan boş olamaz.")
    kimlik_sifreli, kimlik_ozet, iletisim_sifreli = _sifreli_alanlar(
        conn, buro_id=kullanici.buro_id, muvekkil_id=muvekkil_id, tur=tur, kimlik_no=kimlik_no, iletisim=iletisim)

    eski_kimlik = kripto.coz(eski.kimlik_no_sifreli, kayit_id=eski.id, alan="kimlik_no")         if eski.kimlik_no_sifreli else None
    eski_iletisim = json.loads(kripto.coz(eski.iletisim_sifreli, kayit_id=eski.id, alan="iletisim"))         if eski.iletisim_sifreli else {}
    yeni_kimlik = _kimlik_no_dogrula(tur, kimlik_no) if kimlik_no and kimlik_no.strip() else None
    yeni_iletisim = _iletisim_temizle(iletisim)
    degisen = [ad for ad, once, sonra in (
        ("tur", eski.tur, tur), ("ad_unvan", eski.ad_unvan, ad_unvan), ("kimlik_no", eski_kimlik, yeni_kimlik),
        *((k, eski_iletisim.get(k), yeni_iletisim.get(k)) for k in ("telefon", "e_posta", "adres")),
    ) if once != sonra]
    if not degisen:
        return
    try:
        with conn.begin_nested():
            conn.execute(
                text("UPDATE muvekkil SET tur = :t, ad_unvan = :a, kimlik_no_sifreli = :ks, "
                     "iletisim_sifreli = :is, kimlik_no_ozet = :ko WHERE id = :m"),
                {"t": tur, "a": ad_unvan, "ks": kimlik_sifreli, "is": iletisim_sifreli, "ko": kimlik_ozet,
                 "m": muvekkil_id},
            )
    except IntegrityError:
        raise BelgeHatasi(409, "Bu kimlik numarasıyla kayıtlı müvekkil var.")
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="guncelleme",
                hedef_tur="muvekkil", hedef_id=muvekkil_id, ip_adresi=ip_adresi, ayrinti={"alanlar": degisen})


def _gorunur_muvekkil_kosulu() -> str:
    # Stajyer yalnızca erişimi olan dosyaların müvekkillerini görür
    return (
        "m.buro_id = :b AND (:genis OR EXISTS (SELECT 1 FROM dava_dosyasi d JOIN dosya_erisim e "
        "ON e.dava_dosyasi_id = d.id AND e.kullanici_id = :k WHERE d.muvekkil_id = m.id))"
    )


def muvekkilleri_listele(conn: Connection, *, kullanici_id: UUID, ip_adresi: str | None) -> list[dict]:
    kullanici = kullanici_al(conn, kullanici_id)
    satirlar = conn.execute(
        text(
            "SELECT m.id, m.tur, m.ad_unvan, m.kimlik_no_sifreli, m.olusturma, "
            "(SELECT count(*) FROM dava_dosyasi d WHERE d.muvekkil_id = m.id) AS dava_sayisi "
            f"FROM muvekkil m WHERE {_gorunur_muvekkil_kosulu()} ORDER BY m.ad_unvan"
        ),
        {"b": kullanici.buro_id, "k": kullanici_id, "genis": kullanici.rol in OLUSTURABILEN_ROLLER},
    ).all()
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="muvekkil_listesi", hedef_id=None, ip_adresi=ip_adresi)
    return [
        {
            "id": s.id, "tur": s.tur, "ad_unvan": s.ad_unvan, "dava_sayisi": s.dava_sayisi, "olusturma": s.olusturma,
            "kimlik_no_maskeli": maskele(kripto.coz(s.kimlik_no_sifreli, kayit_id=s.id, alan="kimlik_no"))
            if s.kimlik_no_sifreli else None,
        }
        for s in satirlar
    ]


def muvekkil_ayrintisi(conn: Connection, *, muvekkil_id: UUID, kullanici_id: UUID, ip_adresi: str | None) -> dict:
    kullanici = kullanici_al(conn, kullanici_id)
    m = conn.execute(
        text(
            "SELECT m.id, m.tur, m.ad_unvan, m.kimlik_no_sifreli, m.iletisim_sifreli, m.olusturma "
            f"FROM muvekkil m WHERE m.id = :m AND {_gorunur_muvekkil_kosulu()}"
        ),
        {"m": muvekkil_id, "b": kullanici.buro_id, "k": kullanici_id,
         "genis": kullanici.rol in OLUSTURABILEN_ROLLER},
    ).one_or_none()
    if m is None:
        raise ErisimReddi(404, "Müvekkil bulunamadı.", "bulunamadi")
    davalar = conn.execute(
        text(
            "SELECT d.id, d.dosya_no, d.baslik, d.durum FROM dava_dosyasi d "
            "LEFT JOIN dosya_erisim e ON e.dava_dosyasi_id = d.id AND e.kullanici_id = :k "
            "WHERE d.muvekkil_id = :m AND (:yonetici OR e.kullanici_id IS NOT NULL) ORDER BY d.dosya_no"
        ),
        {"m": muvekkil_id, "k": kullanici_id, "yonetici": kullanici.rol == "yonetici"},
    ).mappings().all()
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="goruntuleme",
                hedef_tur="muvekkil", hedef_id=muvekkil_id, ip_adresi=ip_adresi)
    return {
        "id": m.id, "tur": m.tur, "ad_unvan": m.ad_unvan, "olusturma": m.olusturma,
        "kimlik_no": kripto.coz(m.kimlik_no_sifreli, kayit_id=m.id, alan="kimlik_no") if m.kimlik_no_sifreli else None,
        "iletisim": json.loads(kripto.coz(m.iletisim_sifreli, kayit_id=m.id, alan="iletisim"))
        if m.iletisim_sifreli else {},
        "davalar": [dict(d) for d in davalar],
    }


# --- Dava dosyası ---------------------------------------------------------

def dava_olustur(
    conn: Connection,
    *,
    kullanici_id: UUID,
    muvekkil_id: UUID,
    dosya_no: str,
    baslik: str,
    dava_turu: str | None,
    ip_adresi: str | None,
) -> dict:
    kullanici = kullanici_al(conn, kullanici_id)
    _olusturabilir_mi(kullanici)
    dosya_no, baslik = dosya_no.strip(), baslik.strip()
    if not dosya_no or not baslik:
        raise BelgeHatasi(422, "Dosya numarası ve başlık boş olamaz.")
    muvekkil_burosu = conn.execute(
        text("SELECT buro_id FROM muvekkil WHERE id = :m"), {"m": muvekkil_id}
    ).scalar_one_or_none()
    if muvekkil_burosu != kullanici.buro_id:
        raise BelgeHatasi(422, "Müvekkil bulunamadı.")
    try:
        with conn.begin_nested():
            dava_id = conn.execute(
                text(
                    "INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, dava_turu, "
                    "olusturan_kullanici_id) VALUES (:b, :m, :n, :t, :tur, :k) RETURNING id"
                ),
                {"b": kullanici.buro_id, "m": muvekkil_id, "n": dosya_no, "t": baslik,
                 "tur": (dava_turu or "").strip() or None, "k": kullanici_id},
            ).scalar_one()
    except IntegrityError:
        raise BelgeHatasi(409, f"{dosya_no} numaralı dosya zaten var.")
    # Oluşturan kişi dosyanın sorumlusu olur
    conn.execute(
        text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, 'sorumlu')"),
        {"d": dava_id, "k": kullanici_id},
    )
    denetim_yaz(conn, buro_id=kullanici.buro_id, kullanici_id=kullanici_id, eylem="olusturma",
                hedef_tur="dava_dosyasi", hedef_id=dava_id, ip_adresi=ip_adresi)
    return {"id": dava_id}


DAVA_DURUMLARI = {"acik", "beklemede", "kapali"}


def dava_duzenleyebilir_mi(conn: Connection, dava_id: UUID, kullanici) -> bool:
    """Dosyanın sorumlusu ya da büro yöneticisi; stajyer sorumlu olsa da düzenleyemez."""
    return kullanici.rol in OLUSTURABILEN_ROLLER and _erisim_yonetebilir(conn, dava_id, kullanici)


def dava_guncelle(
    conn: Connection,
    *,
    kullanici_id: UUID,
    dava_id: UUID,
    muvekkil_id: UUID,
    dosya_no: str,
    baslik: str,
    dava_turu: str | None,
    durum: str,
    ip_adresi: str | None,
) -> None:
    """Dosya bilgilerini ve durumunu değiştirir.

    Kapalı dosya salt okunurdur: yalnızca durumu değiştirilerek (yeniden açılarak) düzenlenebilir.
    Denetime değişen alanların eski ve yeni değerleri yazılır (müvekkil için kimlik).
    """
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    kullanici = kullanici_al(conn, kullanici_id)
    if not dava_duzenleyebilir_mi(conn, dava_id, kullanici):
        raise ErisimReddi(403, "Dosyayı yalnızca sorumlusu ya da büro yöneticisi düzenleyebilir.", "yetki_yok")
    if durum not in DAVA_DURUMLARI:
        raise BelgeHatasi(422, "Geçersiz durum.")
    dosya_no, baslik = dosya_no.strip(), baslik.strip()
    if not dosya_no or not baslik:
        raise BelgeHatasi(422, "Dosya numarası ve başlık boş olamaz.")
    dava_turu = (dava_turu or "").strip() or None
    eski = conn.execute(
        text("SELECT muvekkil_id, dosya_no, baslik, dava_turu, durum FROM dava_dosyasi WHERE id = :d FOR UPDATE"),
        {"d": dava_id},
    ).one()
    if muvekkil_id != eski.muvekkil_id:
        muvekkil_burosu = conn.execute(
            text("SELECT buro_id FROM muvekkil WHERE id = :m"), {"m": muvekkil_id}
        ).scalar_one_or_none()
        if muvekkil_burosu != buro_id:
            raise BelgeHatasi(422, "Müvekkil bulunamadı.")
    degisen = {
        ad: [str(once) if isinstance(once, UUID) else once, str(sonra) if isinstance(sonra, UUID) else sonra]
        for ad, once, sonra in (
            ("muvekkil_id", eski.muvekkil_id, muvekkil_id), ("dosya_no", eski.dosya_no, dosya_no),
            ("baslik", eski.baslik, baslik), ("dava_turu", eski.dava_turu, dava_turu), ("durum", eski.durum, durum),
        )
        if once != sonra
    }
    if not degisen:
        return
    if eski.durum == "kapali" and durum == "kapali":
        raise BelgeHatasi(409, DOSYA_KAPALI)
    try:
        with conn.begin_nested():
            conn.execute(
                text("UPDATE dava_dosyasi SET muvekkil_id = :m, dosya_no = :n, baslik = :t, dava_turu = :tur, "
                     "durum = :durum, guncelleme = now() WHERE id = :d"),
                {"m": muvekkil_id, "n": dosya_no, "t": baslik, "tur": dava_turu, "durum": durum, "d": dava_id},
            )
    except IntegrityError:
        raise BelgeHatasi(409, f"{dosya_no} numaralı dosya zaten var.")
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="guncelleme", hedef_tur="dava_dosyasi",
                hedef_id=dava_id, ip_adresi=ip_adresi, ayrinti={"alanlar": degisen})


# --- Dosya erişimi --------------------------------------------------------

def _erisim_yonetebilir(conn: Connection, dava_id: UUID, kullanici) -> bool:
    if kullanici.rol == "yonetici":
        return True
    rol = conn.execute(
        text("SELECT rol FROM dosya_erisim WHERE dava_dosyasi_id = :d AND kullanici_id = :k"),
        {"d": dava_id, "k": kullanici.id},
    ).scalar_one_or_none()
    return rol == "sorumlu"


def erisimleri_listele(conn: Connection, *, dava_id: UUID, kullanici_id: UUID) -> dict:
    dava_erisimini_denetle(conn, dava_id, kullanici_id)
    kullanici = kullanici_al(conn, kullanici_id)
    erisimler = conn.execute(
        text(
            "SELECT k.id AS kullanici_id, k.ad_soyad, k.rol, e.rol AS erisim_rolu, e.verilme "
            "FROM dosya_erisim e JOIN kullanici k ON k.id = e.kullanici_id "
            "WHERE e.dava_dosyasi_id = :d ORDER BY e.rol DESC, k.ad_soyad"
        ),
        {"d": dava_id},
    ).mappings().all()
    return {"erisimler": [dict(e) for e in erisimler], "yonetebilir": _erisim_yonetebilir(conn, dava_id, kullanici)}


def _yonetim_on_kosulu(conn: Connection, dava_id: UUID, kullanici_id: UUID, hedef_id: UUID):
    buro_id = dava_erisimini_denetle(conn, dava_id, kullanici_id)
    kullanici = kullanici_al(conn, kullanici_id)
    if not _erisim_yonetebilir(conn, dava_id, kullanici):
        raise ErisimReddi(403, "Bu dosyanın erişimlerini yalnızca yönetici ya da dosya sorumlusu değiştirebilir.",
                          "yetki_yok")
    hedef_burosu = conn.execute(
        text("SELECT buro_id FROM kullanici WHERE id = :k AND aktif"), {"k": hedef_id}
    ).scalar_one_or_none()
    if hedef_burosu != buro_id:
        raise BelgeHatasi(422, "Kullanıcı bulunamadı.")
    return buro_id


def _son_sorumlu_mu(conn: Connection, dava_id: UUID, hedef_id: UUID) -> bool:
    sorumlular = conn.execute(
        text("SELECT kullanici_id FROM dosya_erisim WHERE dava_dosyasi_id = :d AND rol = 'sorumlu' FOR UPDATE"),
        {"d": dava_id},
    ).scalars().all()
    return sorumlular == [hedef_id]


def erisim_ver(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, hedef_id: UUID, rol: str, ip_adresi: str | None
) -> None:
    if rol not in ERISIM_ROLLERI:
        raise BelgeHatasi(422, "Geçersiz erişim rolü.")
    buro_id = _yonetim_on_kosulu(conn, dava_id, kullanici_id, hedef_id)
    if rol != "sorumlu" and _son_sorumlu_mu(conn, dava_id, hedef_id):
        raise BelgeHatasi(409, "Dosyanın son sorumlusu inceleyen yapılamaz; önce başka bir sorumlu ekleyin.")
    conn.execute(
        text(
            "INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, :r) "
            "ON CONFLICT (dava_dosyasi_id, kullanici_id) DO UPDATE SET rol = EXCLUDED.rol"
        ),
        {"d": dava_id, "k": hedef_id, "r": rol},
    )
    denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="erisim_degisikligi",
                hedef_tur="dava_dosyasi", hedef_id=dava_id, ip_adresi=ip_adresi,
                ayrinti={"kullanici_id": str(hedef_id), "rol": rol})


def erisim_kaldir(
    conn: Connection, *, dava_id: UUID, kullanici_id: UUID, hedef_id: UUID, ip_adresi: str | None
) -> None:
    buro_id = _yonetim_on_kosulu(conn, dava_id, kullanici_id, hedef_id)
    if _son_sorumlu_mu(conn, dava_id, hedef_id):
        raise BelgeHatasi(409, "Dosyanın son sorumlusu kaldırılamaz; önce başka bir sorumlu ekleyin.")
    silinen = conn.execute(
        text("DELETE FROM dosya_erisim WHERE dava_dosyasi_id = :d AND kullanici_id = :k"),
        {"d": dava_id, "k": hedef_id},
    ).rowcount
    if silinen:
        denetim_yaz(conn, buro_id=buro_id, kullanici_id=kullanici_id, eylem="erisim_degisikligi",
                    hedef_tur="dava_dosyasi", hedef_id=dava_id, ip_adresi=ip_adresi,
                    ayrinti={"kullanici_id": str(hedef_id), "rol": None})


def buro_kullanicilari(conn: Connection, *, kullanici_id: UUID) -> list[dict]:
    kullanici = kullanici_al(conn, kullanici_id)
    return [dict(s) for s in conn.execute(
        text("SELECT id, ad_soyad, rol FROM kullanici WHERE buro_id = :b AND aktif ORDER BY ad_soyad"),
        {"b": kullanici.buro_id},
    ).mappings().all()]
