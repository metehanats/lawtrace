"""Metin çıkarma ve OCR görevleri.

Bekleyen 'metin_cikarma' ve 'ocr' görevlerini veritabanından alıp işler. Kuyruk olarak
şimdilik isleme_gorevi tablosu kullanılır (FOR UPDATE SKIP LOCKED); böylece
birden fazla işçi aynı görevi almaz. Redis tabanlı kuyruğa geçildiğinde
gorevi_isle() aynen kullanılabilir.

Sayfa kuralları:
- PDF: her fiziksel sayfa bir belge_sayfa kaydıdır.
- Word: dosyada sayfa bilgisi yoktur; yalnızca elle eklenmiş sayfa sonları
  sayfa ayırır. Bu yüzden Word sayfa numaraları yaklaşıktır.
- Metni boş çıkan PDF sayfaları (taranmış görüntü) için bir 'ocr' görevi açılır
  ve belge 'hazir' durumuna geçmez. OCR görevi yalnızca bu sayfaları işler;
  sayfaların metin_kaynagi 'ocr' olur ve ocr_guven_skoru doldurulur. OCR'dan
  sonra da boş kalan sayfanın skoru NULL'dır (boş sayfa ya da okunamayan görüntü).

Yeniden deneme:
- Kalıcı hata: dosya içeriği çözümlenemiyor (bozuk PDF/Word). Aynı baytlar her
  denemede aynı sonucu vereceği için yeniden denenmez; görev hemen 'hata' olur.
- Geçici hata: geri kalan her şey (depolama okunamadı, bağlantı sorunu vb.).
  Görev 'bekliyor' durumuna döner ve artan bekleme süresinden sonra yeniden
  alınır. MAKS_DENEME kez başarısız olursa 'hata' olur.
- Bekleme süresi ayrı bir sütunda tutulmaz; son denemenin bitiş zamanından
  (bitis) ve başarısız deneme sayısından (tekrar_sayisi) hesaplanır.
"""

import io
from uuid import UUID

import docx
from docx.oxml.ns import qn
from pypdf import PdfReader
from sqlalchemy import Connection, text

from app import ayarlar
from app.analiz import ozel_nitelik
from app.belge import ocr
from app.belge.depolama import Depolama
from app.belge.yukleme import DOCX, PDF


class KaliciHata(Exception):
    """Yeniden denemenin sonucu değiştirmeyeceği hata."""


def _temizle(metin: str) -> str:
    # PostgreSQL metin alanları NUL karakteri kabul etmez
    return metin.replace("\x00", "").strip()


def _pdf_sayfalari(veri: bytes) -> list[str]:
    okuyucu = PdfReader(io.BytesIO(veri))
    return [_temizle(sayfa.extract_text() or "") for sayfa in okuyucu.pages]


def _sayfa_sonu_var(paragraf) -> bool:
    return any(
        br.get(qn("w:type")) == "page" for br in paragraf._element.iter(qn("w:br"))
    )


def _docx_sayfalari(veri: bytes) -> list[str]:
    belge = docx.Document(io.BytesIO(veri))
    sayfalar: list[list[str]] = [[]]
    for paragraf in belge.paragraphs:
        if paragraf.text:
            sayfalar[-1].append(paragraf.text)
        if _sayfa_sonu_var(paragraf):
            sayfalar.append([])
    if len(sayfalar) > 1 and not sayfalar[-1]:
        sayfalar.pop()
    return [_temizle("\n".join(satirlar)) for satirlar in sayfalar]


def sayfalari_cikar(mime_tur: str, veri: bytes) -> list[str]:
    """Belgeyi sayfa metinlerine ayırır. Çözümleme hataları KaliciHata olarak yükseltilir."""
    if mime_tur not in (PDF, DOCX):
        raise KaliciHata(f"Desteklenmeyen tür: {mime_tur}")
    try:
        sayfalar = _pdf_sayfalari(veri) if mime_tur == PDF else _docx_sayfalari(veri)
    except Exception as hata:
        raise KaliciHata(f"Belge çözümlenemedi ({type(hata).__name__}: {hata})") from hata
    if not sayfalar:
        raise KaliciHata("Belgede sayfa bulunamadı.")
    return sayfalar


TUM_ADIMLAR = ("metin_cikarma", "ocr", "analiz")


def _sonraki_gorevi_al(conn: Connection, adimlar: tuple[str, ...]):
    # Daha önce başarısız olmuş görev, bekleme süresi dolmadan alınmaz
    return conn.execute(
        text(
            "SELECT g.id, g.adim, g.belge_id, g.tekrar_sayisi, g.analiz_calistirmasi_id, "
            "b.mime_tur, b.depolama_anahtari "
            "FROM isleme_gorevi g JOIN belge b ON b.id = g.belge_id "
            "WHERE g.adim = ANY(:adimlar) AND g.durum = 'bekliyor' "
            "AND (g.tekrar_sayisi = 0 OR g.bitis <= now() - "
            "     make_interval(secs => :taban * power(2, g.tekrar_sayisi - 1))) "
            "ORDER BY b.yuklenme "
            "LIMIT 1 FOR UPDATE OF g SKIP LOCKED"
        ),
        {"taban": ayarlar.YENIDEN_DENEME_TABAN_SANIYE, "adimlar": list(adimlar)},
    ).one_or_none()


def _ozel_nitelik_denetle(conn: Connection, belge_id) -> None:
    """Metni hazır olan belgede özel nitelikli veri işareti arar; bulursa belgeyi işaretler.

    Yalnızca işaret koyar, kaldırmaz (avukatın elle koyduğu işaret korunur).
    """
    metinler = conn.execute(
        text("SELECT metin FROM belge_sayfa WHERE belge_id = :b ORDER BY sayfa_no"), {"b": belge_id}
    ).scalars().all()
    neden = ozel_nitelik.tespit_et(metinler)
    if neden:
        conn.execute(
            text("UPDATE belge SET ozel_nitelikli = true, ozel_nitelik_nedeni = :n "
                 "WHERE id = :b AND NOT ozel_nitelikli"),
            {"b": belge_id, "n": f"Otomatik tespit: {neden}"},
        )


def _metin_cikar(conn: Connection, gorev, veri: bytes) -> None:
    sayfalar = sayfalari_cikar(gorev.mime_tur, veri)
    for no, metin in enumerate(sayfalar, start=1):
        conn.execute(
            text(
                "INSERT INTO belge_sayfa (belge_id, sayfa_no, metin, metin_kaynagi) "
                "VALUES (:b, :no, :metin, 'dogrudan')"
            ),
            {"b": gorev.belge_id, "no": no, "metin": metin},
        )
    ocr_gerekli = gorev.mime_tur == PDF and any(not m for m in sayfalar)
    if ocr_gerekli:
        conn.execute(
            text("INSERT INTO isleme_gorevi (belge_id, adim) VALUES (:b, 'ocr')"),
            {"b": gorev.belge_id},
        )
    conn.execute(
        text("UPDATE belge SET sayfa_sayisi = :n, durum = :durum WHERE id = :b"),
        {
            "b": gorev.belge_id,
            "n": len(sayfalar),
            "durum": "isleniyor" if ocr_gerekli else "hazir",
        },
    )
    _ozel_nitelik_denetle(conn, gorev.belge_id)


def _ocr_uygula(conn: Connection, gorev, veri: bytes) -> None:
    """Metin çıkarmada boş kalan PDF sayfalarını OCR ile doldurur."""
    sayfalar = conn.execute(
        text(
            "SELECT id, sayfa_no FROM belge_sayfa "
            "WHERE belge_id = :b AND metin_kaynagi = 'dogrudan' AND metin = '' ORDER BY sayfa_no"
        ),
        {"b": gorev.belge_id},
    ).all()
    try:
        goruntuleyici = ocr.PdfGoruntuleyici(veri)
    except Exception as hata:
        raise KaliciHata(f"PDF görüntülenemedi ({type(hata).__name__}: {hata})") from hata

    with goruntuleyici:
        for sayfa in sayfalar:
            try:
                goruntu = goruntuleyici.sayfa(sayfa.sayfa_no, ayarlar.OCR_DPI)
            except Exception as hata:
                raise KaliciHata(
                    f"Sayfa {sayfa.sayfa_no} görüntülenemedi ({type(hata).__name__}: {hata})"
                ) from hata
            # Tesseract hataları (kurulu değil, zaman aşımı) geçici sayılır
            metin, guven = ocr.sayfayi_oku(goruntu)
            conn.execute(
                text(
                    "UPDATE belge_sayfa SET metin = :m, metin_kaynagi = 'ocr', ocr_guven_skoru = :g "
                    "WHERE id = :s"
                ),
                {"s": sayfa.id, "m": metin, "g": guven},
            )
    conn.execute(text("UPDATE belge SET durum = 'hazir' WHERE id = :b"), {"b": gorev.belge_id})
    _ozel_nitelik_denetle(conn, gorev.belge_id)


def _analiz(conn: Connection, gorev, _veri: bytes) -> None:
    from app.analiz.gorev import AnalizHatasi, analiz_uygula

    try:
        analiz_uygula(conn, gorev.analiz_calistirmasi_id)
    except AnalizHatasi as hata:
        raise KaliciHata(str(hata)) from hata


ISLEYICILER = {"metin_cikarma": _metin_cikar, "ocr": _ocr_uygula, "analiz": _analiz}
# Belgenin durumunu (yuklendi/isleniyor/hazir/hata) yalnızca metin hazırlama adımları değiştirir;
# analiz başarısız olsa da belgenin metni hazırdır.
BELGE_DURUMUNU_ETKILEYEN = {"metin_cikarma", "ocr"}


def gorevi_isle(conn: Connection, depolama: Depolama, adimlar: tuple[str, ...] = TUM_ADIMLAR) -> UUID | None:
    """Bekleyen bir görevi (metin çıkarma, OCR ya da analiz) işler. İşlenecek görev yoksa None döner.

    adimlar: bu çağrının alacağı görev türleri (ör. analiz ayrı bir işçide çalıştırılacaksa).
    Çağıran taraf conn üzerinde bir işlem (transaction) açmış olmalıdır.
    """
    gorev = _sonraki_gorevi_al(conn, adimlar)
    if gorev is None:
        return None
    belgeyi_etkiler = gorev.adim in BELGE_DURUMUNU_ETKILEYEN

    conn.execute(
        text("UPDATE isleme_gorevi SET durum = 'calisiyor', baslangic = now() WHERE id = :g"),
        {"g": gorev.id},
    )
    if belgeyi_etkiler:
        conn.execute(
            text("UPDATE belge SET durum = 'isleniyor' WHERE id = :b"), {"b": gorev.belge_id}
        )

    try:
        with conn.begin_nested():
            # Analiz dosyanın kendisine değil, çıkarılmış sayfa metinlerine bakar
            veri = depolama.oku(gorev.depolama_anahtari) if belgeyi_etkiler else b""
            ISLEYICILER[gorev.adim](conn, gorev, veri)
            conn.execute(
                text("UPDATE isleme_gorevi SET durum = 'tamam', bitis = now() WHERE id = :g"),
                {"g": gorev.id},
            )
    except Exception as hata:
        yeniden_denenecek = (
            not isinstance(hata, KaliciHata) and gorev.tekrar_sayisi + 1 < ayarlar.MAKS_DENEME
        )
        conn.execute(
            text(
                "UPDATE isleme_gorevi SET durum = :durum, bitis = now(), "
                "hata_mesaji = :m, tekrar_sayisi = tekrar_sayisi + 1 WHERE id = :g"
            ),
            {
                "g": gorev.id,
                "durum": "bekliyor" if yeniden_denenecek else "hata",
                "m": f"{type(hata).__name__}: {hata}"[:1000],
            },
        )
        if belgeyi_etkiler:
            # Yeniden deneme bekleyen belge 'isleniyor' durumunda kalır
            conn.execute(
                text("UPDATE belge SET durum = :durum WHERE id = :b"),
                {"b": gorev.belge_id, "durum": "isleniyor" if yeniden_denenecek else "hata"},
            )
        elif not yeniden_denenecek and gorev.analiz_calistirmasi_id:
            conn.execute(
                text("UPDATE analiz_calistirmasi SET durum = 'hata', bitis = now() WHERE id = :a"),
                {"a": gorev.analiz_calistirmasi_id},
            )

    return gorev.id
