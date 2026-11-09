"""Arayüz (uçtan uca) testleri için ayrı veritabanıyla API sunucusu.

YALNIZCA YEREL TEST İÇİNDİR. Her çalıştırmada:
1. "lawtrace_e2e" veritabanı silinip yeniden oluşturulur (geliştirme veritabanına dokunulmaz),
2. migrasyonlar uygulanır ve sentetik demo verisi (araclar/demo_veri.py) yüklenir,
3. ilk demo dosyası (2025/1487) YALNIZCA KURALLARLA analiz edilir: model yerine boş yanıt veren bir
   sahte model kullanılır, böylece testler Ollama'ya bağlı kalmaz ve bulgular her seferinde aynıdır,
4. API bu veritabanıyla --port üzerinde başlatılır.

Belgeler %USERPROFILE%\\AvukatDosyaTakipVeri\\e2e\\depolama altına yazılır ve her seferinde silinir.
Gerçek müvekkil anahtarı kullanılmaz; sabit bir TEST anahtarıyla şifrelenir (tests/conftest.py ile aynı).
Veritabanı oluşturmak için postgres rolü gerekir (AVUKAT_PG_SUPERPW).

    python araclar/e2e_sunucu.py --port 8100     # frontend/playwright.config.ts bunu çağırır
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
from sqlalchemy import make_url

KOK = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(KOK))

from app import ayarlar  # noqa: E402

E2E_DB = "lawtrace_e2e"
TEST_ANAHTARI = "dGVzdC1hbmFodGFyaS0zMi1iYXl0LXVnbnVsZXItMDA"


def _kullanici_ortami(ad: str) -> str | None:
    """Önce süreç ortamı; yoksa Windows kullanıcı ortam değişkeni (terminal değişken tanımlanmadan açılmışsa)."""
    if deger := os.environ.get(ad):
        return deger
    if sys.platform == "win32":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as anahtar:
                return winreg.QueryValueEx(anahtar, ad)[0]
        except OSError:
            return None
    return None


def _ortam(kaynak_url: str) -> dict[str, str]:
    url = make_url(kaynak_url).set(database=E2E_DB).render_as_string(hide_password=False)
    veri = ayarlar.veri_koku() / "e2e"
    return {**os.environ, "DATABASE_URL": url, "DEPOLAMA_KOKU": str(veri / "depolama"),
            "MUVEKKIL_ANAHTARI": TEST_ANAHTARI, "PYTHONIOENCODING": "utf-8"}


def hazirla() -> dict[str, str]:
    kaynak = _kullanici_ortami("DATABASE_URL")
    if not kaynak:
        sys.exit("DATABASE_URL tanımlı değil.")
    parola = _kullanici_ortami("AVUKAT_PG_SUPERPW")
    if not parola:
        sys.exit("AVUKAT_PG_SUPERPW tanımlı değil (test veritabanı oluşturmak için gerekli).")
    u = make_url(kaynak)
    if u.database == E2E_DB:
        sys.exit("DATABASE_URL zaten test veritabanını gösteriyor; geliştirme veritabanının adresi beklenir.")
    with psycopg.connect(dbname="postgres", host=u.host or "localhost", port=u.port or 5432, user="postgres",
                         password=parola, autocommit=True) as c:
        c.execute(f'DROP DATABASE IF EXISTS "{E2E_DB}" WITH (FORCE)')
        c.execute(f'CREATE DATABASE "{E2E_DB}" OWNER "{u.username}"')
    ortam = _ortam(kaynak)
    shutil.rmtree(ortam["DEPOLAMA_KOKU"], ignore_errors=True)
    python = sys.executable
    subprocess.run([python, "-m", "alembic", "-c", "db/alembic.ini", "upgrade", "head"], cwd=KOK, env=ortam, check=True)
    subprocess.run([python, "araclar/demo_veri.py"], cwd=KOK, env=ortam, check=True)
    subprocess.run([python, "araclar/e2e_sunucu.py", "--kural-analizi"], cwd=KOK, env=ortam, check=True)
    return ortam


class _BosModel:
    """Model adımı boş döner; bulgular yalnızca kurallardan (tarih/tutar) gelir."""
    saglayici, model = "ollama", "e2e-sahte"

    def json_tamamla(self, sistem, kullanici, sema):
        return {"bulgular": []}


def kural_analizi() -> None:
    """Test veritabanında (ortam e2e'ye ayarlıyken çağrılır) ilk demo dosyasını kurallarla analiz eder."""
    from sqlalchemy import text

    from app.analiz import gorev, hizmet
    from app.belge.api import depolama_al
    from app.belge.isci import bekleyenleri_isle
    from app.db import engine

    if make_url(os.environ["DATABASE_URL"]).database != E2E_DB:
        sys.exit("Kural analizi yalnızca test veritabanında çalışır.")
    gorev.model_olustur = lambda tanim: _BosModel()
    with engine().begin() as c:
        dava, avukat = c.execute(text(
            "SELECT d.id, k.id FROM dava_dosyasi d JOIN kullanici k ON k.buro_id = d.buro_id "
            "WHERE d.dosya_no = '2025/1487' AND k.e_posta = 'avukat@demo.test'")).one()
        # Demo dosyasındaki özel nitelikli belge varsa analiz için onay verilmiş sayılır (yalnızca test)
        c.execute(text("UPDATE belge SET ozel_nitelik_onay_kullanici_id = :k, ozel_nitelik_onay_zamani = now() "
                       "WHERE dava_dosyasi_id = :d AND ozel_nitelikli"), {"k": avukat, "d": dava})
        hizmet.analiz_baslat(c, dava_id=dava, kullanici_id=avukat, belge_idleri=None, ip_adresi=None)
    print(f"Kural analizi: {bekleyenleri_isle(engine().begin, depolama_al())} görev işlendi.")


def main() -> None:
    ayristirici = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ayristirici.add_argument("--port", type=int, default=8100)
    ayristirici.add_argument("--kural-analizi", action="store_true", help=argparse.SUPPRESS)
    secenek = ayristirici.parse_args()
    if secenek.kural_analizi:
        kural_analizi()
        return
    ortam = hazirla()
    print(f"Test API'si: http://127.0.0.1:{secenek.port} (veritabanı {E2E_DB})", flush=True)
    sys.exit(subprocess.call([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1",
                              "--port", str(secenek.port)], cwd=KOK, env=ortam))


if __name__ == "__main__":
    main()
