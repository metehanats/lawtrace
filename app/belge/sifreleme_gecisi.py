"""Şifresiz saklanmış eski belge dosyalarını bir kez şifreler.

Her belge için:
1. Dosya zaten şifreliyse atlanır (araç tekrar çalıştırılabilir).
2. Şifresiz dosyanın SHA-256 özeti veritabanındaki özetle karşılaştırılır; uymazsa dosyaya
   dokunulmaz ve rapor edilir (bozuk ya da yanlış dosya şifrelenip "doğrulanmış" görünmesin).
3. Şifreli hali yazılır (geçici dosya + yer değiştirme), geri okunup çözülür ve özet yeniden
   denetlenir.
Veritabanında kaydı olmayan dosyalara dokunulmaz, sayıları rapor edilir.

    python -m app.belge.sifreleme_gecisi --deneme   # yalnızca ne yapılacağını say
    python -m app.belge.sifreleme_gecisi            # şifrele
"""

import argparse
import hashlib
from dataclasses import dataclass, field

from sqlalchemy import Connection, text

from app import ayarlar, kripto
from app.belge.depolama import SifreliDepolama, YerelDepolama


@dataclass
class Rapor:
    sifrelenen: int = 0
    zaten_sifreli: int = 0
    dosyasi_yok: list[str] = field(default_factory=list)
    ozet_uyusmayan: list[str] = field(default_factory=list)
    kayitsiz_dosya: int = 0


def gecir(conn: Connection, yerel: YerelDepolama, *, deneme: bool = False) -> Rapor:
    rapor = Rapor()
    sifreli = SifreliDepolama(yerel)
    kayitli = set()
    for b in conn.execute(text("SELECT depolama_anahtari, sha256_ozet FROM belge ORDER BY yuklenme")):
        kayitli.add(b.depolama_anahtari)
        try:
            ham = yerel.oku(b.depolama_anahtari)
        except FileNotFoundError:
            rapor.dosyasi_yok.append(b.depolama_anahtari)
            continue
        if kripto.belge_sifreli_mi(ham):
            rapor.zaten_sifreli += 1
            continue
        if hashlib.sha256(ham).hexdigest() != b.sha256_ozet:
            rapor.ozet_uyusmayan.append(b.depolama_anahtari)
            continue
        if not deneme:
            sifreli.kaydet(b.depolama_anahtari, ham)
            if hashlib.sha256(sifreli.oku(b.depolama_anahtari)).hexdigest() != b.sha256_ozet:
                raise RuntimeError(f"Şifreleme doğrulanamadı: {b.depolama_anahtari}")
        rapor.sifrelenen += 1
    rapor.kayitsiz_dosya = sum(
        1 for yol in yerel.kok.rglob("*")
        if yol.is_file() and not yol.name.endswith(".yaziliyor")
        and yol.relative_to(yerel.kok).as_posix() not in kayitli
    )
    return rapor


def main() -> None:
    from app.db import engine

    ayr = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ayr.add_argument("--deneme", action="store_true", help="hiçbir dosyayı değiştirme, yalnızca say")
    secenek = ayr.parse_args()
    with engine().connect() as conn:
        r = gecir(conn, YerelDepolama(ayarlar.depolama_koku()), deneme=secenek.deneme)
    print(f"{'Şifrelenecek' if secenek.deneme else 'Şifrelenen'}: {r.sifrelenen} · zaten şifreli: {r.zaten_sifreli}")
    if r.dosyasi_yok:
        print(f"Dosyası bulunamayan kayıt: {len(r.dosyasi_yok)}")
    if r.ozet_uyusmayan:
        print(f"ÖZETİ UYUŞMAYAN (dokunulmadı): {len(r.ozet_uyusmayan)}")
    if r.kayitsiz_dosya:
        print(f"Veritabanında kaydı olmayan dosya (dokunulmadı): {r.kayitsiz_dosya}")


if __name__ == "__main__":
    main()
