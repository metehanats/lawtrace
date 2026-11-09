"""Belge işleme işçisi (metin çıkarma ve OCR).

Bekleyen görevleri sırayla işler; görev kalmayınca bir süre bekleyip yeniden bakar.
Her görev kendi işleminde (transaction) işlenir. İşçi görev ortasında çökerse
işlem geri alınır ve görev 'bekliyor' durumunda kalır; bir sonraki turda yeniden alınır.

Birden fazla işçi aynı anda çalıştırılabilir; FOR UPDATE SKIP LOCKED sayesinde
aynı görevi iki işçi almaz.

Çalıştırmak için:
    python -m app.belge.isci              # sürekli çalışır, Ctrl+C ile durur
    python -m app.belge.isci --tek-sefer  # bekleyenleri işler ve çıkar

Günlüğe yalnızca görev kimlikleri yazılır; dosya adı veya belge içeriği yazılmaz.
"""

import argparse
import logging
import signal
import threading
from collections.abc import Callable
from contextlib import AbstractContextManager
from uuid import UUID

from sqlalchemy import Connection

from app import ayarlar
from app.belge.api import depolama_al
from app.belge.depolama import Depolama
from app.belge.metin_cikarma import TUM_ADIMLAR, gorevi_isle
from app.db import engine

gunluk = logging.getLogger("app.belge.isci")

IslemAc = Callable[[], AbstractContextManager[Connection]]


def bekleyenleri_isle(
    islem_ac: IslemAc,
    depolama: Depolama,
    dur: threading.Event | None = None,
    adimlar: tuple[str, ...] = TUM_ADIMLAR,
) -> int:
    """Bekleyen görev kalmayana (ya da durma isteği gelene) kadar işler; işlenen görev sayısını döndürür."""
    sayi = 0
    while not (dur and dur.is_set()):
        with islem_ac() as conn:
            gorev_id = gorevi_isle(conn, depolama, adimlar)
        if gorev_id is None:
            break
        sayi += 1
        gunluk.info("Görev işlendi: %s", gorev_id)
    return sayi


def calistir(
    islem_ac: IslemAc,
    depolama: Depolama,
    dur: threading.Event,
    bekleme_saniye: float,
    adimlar: tuple[str, ...] = TUM_ADIMLAR,
) -> None:
    gunluk.info("İşçi başladı (görevler: %s, bekleme: %s sn).", ", ".join(adimlar), bekleme_saniye)
    while not dur.is_set():
        try:
            bekleyenleri_isle(islem_ac, depolama, dur, adimlar)
        except Exception:
            # Veritabanı bağlantısı kopması gibi durumlarda işçi kapanmaz; bekleyip yeniden dener
            gunluk.exception("Görev turu başarısız oldu; %s sn sonra yeniden denenecek.", bekleme_saniye)
        dur.wait(bekleme_saniye)
    gunluk.info("İşçi durdu.")


def main(argv: list[str] | None = None) -> None:
    ayristirici = argparse.ArgumentParser(description="Belge işleme işçisi")
    ayristirici.add_argument("--tek-sefer", action="store_true", help="Bekleyenleri işle ve çık")
    ayristirici.add_argument(
        "--bekleme", type=float, default=ayarlar.ISCI_BEKLEME_SANIYE,
        help="Görev yokken iki kontrol arasındaki süre (saniye)",
    )
    ayristirici.add_argument(
        "--adimlar", default=",".join(TUM_ADIMLAR),
        help="Alınacak görev türleri, virgülle (ör. yavaş analizi ayrı işçiye almak için: "
             "bir işçide 'metin_cikarma,ocr', ötekinde 'analiz')",
    )
    secenekler = ayristirici.parse_args(argv)
    adimlar = tuple(a.strip() for a in secenekler.adimlar.split(",") if a.strip())
    if not adimlar or set(adimlar) - set(TUM_ADIMLAR):
        ayristirici.error(f"Geçersiz görev türü; seçenekler: {', '.join(TUM_ADIMLAR)}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    depolama = depolama_al()
    if secenekler.tek_sefer:
        sayi = bekleyenleri_isle(engine().begin, depolama, adimlar=adimlar)
        gunluk.info("%d görev işlendi.", sayi)
        return

    dur = threading.Event()

    def durdur(*_):
        # Elindeki görevi bitirir, sonra çıkar
        gunluk.info("Durma isteği alındı; mevcut görev bitince çıkılacak.")
        dur.set()

    signal.signal(signal.SIGINT, durdur)
    signal.signal(signal.SIGTERM, durdur)
    calistir(engine().begin, depolama, dur, secenekler.bekleme, adimlar)


if __name__ == "__main__":
    main()
