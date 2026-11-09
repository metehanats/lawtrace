"""Yedekleme ve yedek doğrulama.

Bir yedek, YEDEK_KLASORU altında "yedek-YYYYMMDD-HHMMSS" klasörüdür:
- veritabani.dump.sifreli  pg_dump (özel biçim) çıktısı, yedek anahtarıyla AES-256-GCM şifreli.
  Döküm diske hiçbir an şifresiz yazılmaz; pg_dump çıktısı bellekte şifrelenir.
- depolama/                belge klasörünün kopyası (dosyalar zaten şifreli; şifresiz dosya
                           bulunursa yedek alınmaz).
- manifest.json            her dosyanın SHA-256 özeti, şema sürümü, belge sayısı ve anahtar izi.
Yedek önce ".yaziliyor" adıyla yazılır, bitince yeniden adlandırılır; yarım yedek tam görünmez.

Yedeği açmak için ŞİFRELEME ANAHTARI GEREKİR (MUVEKKIL_ANAHTARI). Anahtar yedekle aynı yerde
saklanmamalıdır. Manifestteki iz, elinizdeki anahtarın bu yedeğe ait olup olmadığını gösterir.

Doğrulama:
- Hızlı: özetler, anahtar izi ve dökümün okunabilirliği (pg_restore --list).
- Tam (--tam): döküm geçici bir veritabanına geri yüklenir, her belge kaydının dosyası yedekten
  çözülüp özeti karşılaştırılır, geçici veritabanı silinir. Canlı veritabanına dokunulmaz.
  Veritabanı oluşturma yetkisi için postgres rolü kullanılır (parolası AVUKAT_PG_SUPERPW).

    python -m app.yedek al [--hedef KLASÖR] [--dogrula]
    python -m app.yedek dogrula KLASÖR [--tam]
    python -m app.yedek liste
    python -m app.yedek otomatik --sakla 14   # zamanlanmış görev: al + doğrula + eskileri sil + günlük

Otomatik çalışma her denemeyi YEDEK_KLASORU/yedek-gunlugu.jsonl dosyasına yazar; yönetim ekranı
son yedeğin durumunu buradan okur. Eski yedekler yalnızca yeni yedek tam doğrulandıktan sonra silinir.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import psycopg
from sqlalchemy import create_engine, make_url, text

from app import ayarlar, kripto

MANIFEST = "manifest.json"
DOKUM = "veritabani.dump.sifreli"
DEPOLAMA = "depolama"
SURUM = 1


class YedekHatasi(RuntimeError):
    pass


def _pg_baglanti(url: str) -> tuple[list[str], dict, str]:
    u = make_url(url)
    # Parola komut satırına değil ortama konur (süreç listesinde görünmesin)
    return (["-h", u.host or "localhost", "-p", str(u.port or 5432), "-U", u.username or ""],
            {**os.environ, "PGPASSWORD": u.password or ""}, u.database or "")


def _ozet(yol: Path) -> str:
    return hashlib.sha256(yol.read_bytes()).hexdigest()


def _dosyalar(kok: Path) -> dict[str, str]:
    return {p.relative_to(kok).as_posix(): _ozet(p) for p in sorted(kok.rglob("*"))
            if p.is_file() and p.name != MANIFEST}


def yedek_al(hedef_kok: Path, *, depolama_kok: Path, db_url: str) -> Path:
    zaman = datetime.now().astimezone()
    hedef = hedef_kok / f"yedek-{zaman:%Y%m%d-%H%M%S}"
    gecici = hedef.with_name(hedef.name + ".yaziliyor")
    if hedef.exists() or gecici.exists():
        raise YedekHatasi(f"{hedef} zaten var.")
    gecici.mkdir(parents=True)
    try:
        # Belgeler önce: şifresiz dosya varsa döküm almaya gerek kalmadan durulur.
        # rglob okunamayan klasörü sessizce atlar; burada okunamayan her klasör hatadır (eksik yedek olmasın).
        if not depolama_kok.is_dir():
            raise YedekHatasi(f"Belge klasörü bulunamadı: {depolama_kok}")

        def _okunamadi(hata: OSError):
            raise YedekHatasi(f"Belge klasörü okunamadı: {hata}")

        dosyalar = sorted(Path(d) / f for d, _, adlar in os.walk(depolama_kok, onerror=_okunamadi) for f in adlar)
        for yol in dosyalar:
            if yol.name.endswith(".yaziliyor"):
                continue
            veri = yol.read_bytes()
            if not kripto.belge_sifreli_mi(veri):
                raise YedekHatasi(f"Şifresiz belge dosyası var ({yol.relative_to(depolama_kok)}); "
                                  "önce python -m app.belge.sifreleme_gecisi çalıştırın.")
            kopya = gecici / DEPOLAMA / yol.relative_to(depolama_kok)
            kopya.parent.mkdir(parents=True, exist_ok=True)
            kopya.write_bytes(veri)

        args, ortam, db = _pg_baglanti(db_url)
        sonuc = subprocess.run([ayarlar.pg_araci("pg_dump"), *args, "-Fc", "--no-owner", "-d", db],
                               env=ortam, capture_output=True)
        if sonuc.returncode != 0:
            raise YedekHatasi(f"pg_dump başarısız: {sonuc.stderr.decode(errors='replace').strip()}")
        (gecici / DOKUM).write_bytes(kripto.yedek_sifrele(sonuc.stdout, ad=DOKUM))

        motor = create_engine(db_url)
        try:
            with motor.connect() as conn:
                surum = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
                belge_sayisi = conn.execute(text("SELECT count(*) FROM belge")).scalar_one()
        finally:
            motor.dispose()
        manifest = {
            "surum": SURUM, "olusturma": zaman.isoformat(timespec="seconds"), "veritabani": db,
            "sema_surumu": surum, "belge_sayisi": belge_sayisi,
            "anahtar_parmak_izi": kripto.anahtar_parmak_izi(), "dosyalar": _dosyalar(gecici),
        }
        (gecici / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        gecici.rename(hedef)
    except BaseException:
        shutil.rmtree(gecici, ignore_errors=True)
        raise
    return hedef


@dataclass
class Dogrulama:
    manifest: dict
    sorunlar: list[str] = field(default_factory=list)
    dogrulanan_belge: int = 0

    @property
    def tamam(self) -> bool:
        return not self.sorunlar


def dogrula(klasor: Path, *, tam: bool = False, db_url: str | None = None, yonetici_parolasi: str | None = None
            ) -> Dogrulama:
    manifest = json.loads((klasor / MANIFEST).read_text(encoding="utf-8"))
    sonuc = Dogrulama(manifest)
    beklenen, mevcut = manifest["dosyalar"], _dosyalar(klasor)
    for ad in sorted(beklenen.keys() - mevcut.keys()):
        sonuc.sorunlar.append(f"Eksik dosya: {ad}")
    for ad in sorted(mevcut.keys() - beklenen.keys()):
        sonuc.sorunlar.append(f"Manifestte olmayan dosya: {ad}")
    for ad in sorted(beklenen.keys() & mevcut.keys()):
        if beklenen[ad] != mevcut[ad]:
            sonuc.sorunlar.append(f"Özeti değişmiş dosya: {ad}")
    if manifest["anahtar_parmak_izi"] != kripto.anahtar_parmak_izi():
        sonuc.sorunlar.append("Bu yedek başka bir şifreleme anahtarıyla alınmış; mevcut anahtarla açılamaz.")
        return sonuc
    if sonuc.sorunlar:
        return sonuc

    dokum = kripto.yedek_coz((klasor / DOKUM).read_bytes(), ad=DOKUM)
    liste = subprocess.run([ayarlar.pg_araci("pg_restore"), "--list"], input=dokum, capture_output=True)
    if liste.returncode != 0:
        sonuc.sorunlar.append("Veritabanı dökümü okunamıyor (pg_restore --list başarısız).")
        return sonuc
    if tam:
        _tam_dogrula(klasor, dokum, sonuc, db_url or ayarlar.veritabani_url(), yonetici_parolasi)
    return sonuc


def _tam_dogrula(klasor: Path, dokum: bytes, sonuc: Dogrulama, db_url: str, yonetici_parolasi: str | None) -> None:
    if not yonetici_parolasi:
        raise YedekHatasi("Tam doğrulama için AVUKAT_PG_SUPERPW tanımlı olmalı (geçici veritabanı oluşturulur).")
    u = make_url(db_url)
    yonetici = dict(host=u.host or "localhost", port=u.port or 5432, user="postgres", password=yonetici_parolasi)
    gecici_db = f"yedek_dogrulama_{secrets.token_hex(4)}"
    with psycopg.connect(dbname="postgres", autocommit=True, **yonetici) as c:
        c.execute(f'CREATE DATABASE "{gecici_db}"')
    try:
        args, ortam, _ = _pg_baglanti(u.set(username="postgres", password=yonetici_parolasi).render_as_string(False))
        geri = subprocess.run([ayarlar.pg_araci("pg_restore"), *args, "--no-owner", "--no-acl", "-d", gecici_db],
                              input=dokum, env=ortam, capture_output=True)
        if geri.returncode != 0:
            sonuc.sorunlar.append(f"Geri yükleme başarısız: {geri.stderr.decode(errors='replace').strip()[:500]}")
            return
        with psycopg.connect(dbname=gecici_db, **yonetici) as c:
            surum = c.execute("SELECT version_num FROM alembic_version").fetchone()[0]
            belgeler = c.execute("SELECT depolama_anahtari, sha256_ozet FROM belge").fetchall()
        if surum != sonuc.manifest["sema_surumu"]:
            sonuc.sorunlar.append(f"Şema sürümü uyuşmuyor: {surum} / {sonuc.manifest['sema_surumu']}")
        for anahtar, ozet in belgeler:
            yol = klasor / DEPOLAMA / anahtar
            if not yol.is_file():
                sonuc.sorunlar.append(f"Belge kaydının dosyası yedekte yok: {anahtar}")
                continue
            try:
                duz = kripto.belge_coz(yol.read_bytes(), anahtar=anahtar)
            except Exception:
                sonuc.sorunlar.append(f"Belge çözülemedi: {anahtar}")
                continue
            if hashlib.sha256(duz).hexdigest() != ozet:
                sonuc.sorunlar.append(f"Belge özeti uyuşmuyor: {anahtar}")
                continue
            sonuc.dogrulanan_belge += 1
    finally:
        with psycopg.connect(dbname="postgres", autocommit=True, **yonetici) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{gecici_db}" WITH (FORCE)')


_YEDEK_ADI = re.compile(r"yedek-\d{8}-\d{6}")
GUNLUK = "yedek-gunlugu.jsonl"


def yedekler(kok: Path) -> list[Path]:
    """Tamamlanmış yedekler, en yeni önce. Yalnızca bu aracın adlandırdığı ve manifesti olan klasörler."""
    return sorted((p for p in kok.glob("yedek-*")
                   if p.is_dir() and _YEDEK_ADI.fullmatch(p.name) and (p / MANIFEST).is_file()),
                  reverse=True) if kok.exists() else []


def buda(kok: Path, *, sakla: int, koru: Path) -> list[str]:
    """En yeni `sakla` yedek dışındakileri siler; az önce alınan (`koru`) asla silinmez.

    Yalnızca yeni yedek alınıp TAM doğrulandıktan sonra çağrılır; böylece bozuk bir yedek yüzünden
    sağlam eski yedekler silinmez.
    """
    if sakla < 1:
        raise YedekHatasi("En az bir yedek saklanmalı.")
    silinen = []
    for yol in yedekler(kok)[sakla:]:
        if yol.resolve() == koru.resolve():
            continue
        shutil.rmtree(yol)
        silinen.append(yol.name)
    return silinen


def gunluge_yaz(kok: Path, kayit: dict) -> None:
    kok.mkdir(parents=True, exist_ok=True)
    with (kok / GUNLUK).open("a", encoding="utf-8") as f:
        f.write(json.dumps({"zaman": datetime.now().astimezone().isoformat(timespec="seconds"), **kayit},
                           ensure_ascii=False) + "\n")


def durum(kok: Path) -> dict:
    """Yönetim ekranı için: son başarılı yedek, son deneme ve saklanan yedek sayısı."""
    son_deneme, son_basarili = None, None
    gunluk = kok / GUNLUK
    if gunluk.is_file():
        for satir in gunluk.read_text(encoding="utf-8").splitlines():
            try:
                kayit = json.loads(satir)
            except ValueError:
                continue
            son_deneme = kayit
            if kayit.get("durum") == "basarili":
                son_basarili = kayit
    return {"son_basarili": son_basarili, "son_deneme": son_deneme, "yedek_sayisi": len(yedekler(kok))}


def otomatik(kok: Path, *, sakla: int | None) -> dict:
    """Zamanlanmış görevin çalıştırdığı adım: al, tam doğrula, buda, günlüğe yaz."""
    try:
        yol = yedek_al(kok, depolama_kok=ayarlar.depolama_koku(), db_url=ayarlar.veritabani_url())
        d = dogrula(yol, tam=True, yonetici_parolasi=os.environ.get("AVUKAT_PG_SUPERPW"))
        if not d.tamam:
            # Doğrulanamayan yedek sayıma girmesin (sağlam bir eskiyi budatmasın); inceleme için silinmez
            yol.rename(yol.with_name(yol.name + ".hatali"))
            raise YedekHatasi("Doğrulama başarısız: " + "; ".join(d.sorunlar[:3]))
        silinen = buda(kok, sakla=sakla, koru=yol) if sakla else []
    except Exception as hata:
        kayit = {"durum": "hata", "mesaj": str(hata)[:500]}
        gunluge_yaz(kok, kayit)
        return kayit
    kayit = {"durum": "basarili", "klasor": yol.name, "belge_sayisi": d.manifest["belge_sayisi"],
             "dogrulanan_belge": d.dogrulanan_belge, "silinen": silinen}
    gunluge_yaz(kok, kayit)
    return kayit


def _dogrula_yaz(klasor: Path, *, tam: bool) -> None:
    d = dogrula(klasor, tam=tam, yonetici_parolasi=os.environ.get("AVUKAT_PG_SUPERPW"))
    if not d.tamam:
        print("YEDEKTE SORUN VAR:\n  " + "\n  ".join(d.sorunlar))
        sys.exit(1)
    ek = f"; {d.dogrulanan_belge} belge geri yüklenip çözüldü" if tam else ""
    print(f"Yedek sağlam ({len(d.manifest['dosyalar'])} dosya{ek}).")


def main() -> None:
    ayr = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    alt = ayr.add_subparsers(dest="komut", required=True)
    al = alt.add_parser("al", help="yeni yedek al")
    al.add_argument("--hedef", type=Path, default=None, help="varsayılan: YEDEK_KLASORU")
    al.add_argument("--dogrula", action="store_true", help="aldıktan sonra tam doğrula")
    dg = alt.add_parser("dogrula", help="bir yedeği doğrula")
    dg.add_argument("klasor", type=Path)
    dg.add_argument("--tam", action="store_true", help="geçici veritabanına geri yükleyerek doğrula")
    alt.add_parser("liste", help="yedekleri listele")
    ot = alt.add_parser("otomatik", help="al + tam doğrula + eskileri sil + günlüğe yaz (zamanlanmış görev)")
    ot.add_argument("--sakla", type=int, default=None, help="saklanacak yedek sayısı (verilmezse silinmez)")
    secenek = ayr.parse_args()

    try:
        if secenek.komut == "otomatik":
            kayit = otomatik(ayarlar.yedek_klasoru(), sakla=secenek.sakla)
            print(json.dumps(kayit, ensure_ascii=False))
            sys.exit(0 if kayit["durum"] == "basarili" else 1)
        elif secenek.komut == "al":
            yol = yedek_al(secenek.hedef or ayarlar.yedek_klasoru(), depolama_kok=ayarlar.depolama_koku(),
                           db_url=ayarlar.veritabani_url())
            m = json.loads((yol / MANIFEST).read_text(encoding="utf-8"))
            print(f"Yedek alındı: {yol}\n  {m['belge_sayisi']} belge kaydı, {len(m['dosyalar'])} dosya, "
                  f"anahtar izi {m['anahtar_parmak_izi']}")
            if secenek.dogrula:
                _dogrula_yaz(yol, tam=True)
        elif secenek.komut == "dogrula":
            _dogrula_yaz(secenek.klasor, tam=secenek.tam)
        else:
            for yol in yedekler(ayarlar.yedek_klasoru()):
                m = json.loads((yol / MANIFEST).read_text(encoding="utf-8"))
                print(f"{yol.name}  {m['belge_sayisi']} belge  iz {m['anahtar_parmak_izi']}")
    except YedekHatasi as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
