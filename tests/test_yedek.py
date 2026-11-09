"""Yedek alma ve doğrulama testleri. Gerçek pg_dump/pg_restore çalışır; veriler sentetiktir."""

import json
import os
import shutil

import psycopg
import pytest
from sqlalchemy import create_engine, make_url, text

import app.yedek as yedek_mod
from app import ayarlar, kripto
from app.belge.depolama import SifreliDepolama, YerelDepolama
from app.yedek import (
    DOKUM, MANIFEST, Dogrulama, YedekHatasi, buda, dogrula, durum, gunluge_yaz, otomatik, yedek_al, yedekler,
)
from test_kimlik import web  # noqa: F401 (web bir fikstürdür)
from test_yonetici import _oturum, buro  # noqa: F401 (buro bir fikstürdür)

pytestmark = pytest.mark.skipif(shutil.which(ayarlar.pg_araci("pg_dump")) is None, reason="pg_dump yok")


@pytest.fixture
def depolama_kok(tmp_path):
    kok = tmp_path / "depolama"
    SifreliDepolama(YerelDepolama(kok)).kaydet("b/d/1", b"%PDF sentetik belge")
    return kok


def _al(tmp_path, depolama_kok):
    return yedek_al(tmp_path / "yedekler", depolama_kok=depolama_kok, db_url=ayarlar.veritabani_url())


def test_yedek_sifreli_ve_dogrulanabilir(tmp_path, depolama_kok):
    yol = _al(tmp_path, depolama_kok)
    assert yedekler(tmp_path / "yedekler") == [yol]
    m = json.loads((yol / MANIFEST).read_text(encoding="utf-8"))
    assert set(m["dosyalar"]) == {DOKUM, "depolama/b/d/1"}
    assert m["anahtar_parmak_izi"] == kripto.anahtar_parmak_izi()
    # Döküm şifreli: pg_dump imzası ("PGDMP") ve tablo adları açık görünmez
    ham = (yol / DOKUM).read_bytes()
    assert ham.startswith(b"ADT1") and b"PGDMP" not in ham and b"kaynak_alinti" not in ham
    assert dogrula(yol).tamam


def test_bozulan_ya_da_eklenen_dosya_yakalanir(tmp_path, depolama_kok):
    yol = _al(tmp_path, depolama_kok)
    (yol / "depolama/b/d/1").write_bytes(b"ADT1bozuk")
    (yol / "fazla.txt").write_text("x")
    sorunlar = dogrula(yol).sorunlar
    assert "Özeti değişmiş dosya: depolama/b/d/1" in sorunlar and "Manifestte olmayan dosya: fazla.txt" in sorunlar


def test_baska_anahtarla_alinmis_yedek_tanınır(tmp_path, depolama_kok, monkeypatch):
    yol = _al(tmp_path, depolama_kok)
    monkeypatch.setenv("MUVEKKIL_ANAHTARI", kripto.anahtar_uret())
    (sorun,) = dogrula(yol).sorunlar
    assert "başka bir şifreleme anahtarıyla" in sorun


def test_sifresiz_belge_varsa_yedek_alinmaz_yarim_klasor_kalmaz(tmp_path, depolama_kok):
    YerelDepolama(depolama_kok).kaydet("b/d/2", b"%PDF sifresiz")
    with pytest.raises(YedekHatasi, match="Şifresiz belge"):
        _al(tmp_path, depolama_kok)
    assert list((tmp_path / "yedekler").iterdir()) == []


@pytest.mark.skipif(not os.environ.get("AVUKAT_PG_SUPERPW"), reason="AVUKAT_PG_SUPERPW yok")
def test_tam_dogrulama_geri_yukler_her_kaydi_denetler_gecici_veritabanini_siler(tmp_path, depolama_kok):
    # Testler ayrı bir test anahtarıyla çalışır; geliştirme belgeleri gerçek anahtarla şifreli olduğundan
    # burada yedeğe yalnızca sentetik bir dosya konur: veritabanındaki her belge kaydı "dosyası yok"
    # olarak raporlanmalı. Çözme başarılı yolu `python -m app.yedek dogrula --tam` ile elle sınandı.
    yol = _al(tmp_path, depolama_kok)
    parola = os.environ["AVUKAT_PG_SUPERPW"]
    sonuc = dogrula(yol, tam=True, yonetici_parolasi=parola)
    eksik = [s for s in sonuc.sorunlar if s.startswith("Belge kaydının dosyası yedekte yok")]
    assert len(eksik) == len(sonuc.sorunlar) == sonuc.manifest["belge_sayisi"]
    u = make_url(ayarlar.veritabani_url())
    with psycopg.connect(dbname="postgres", host=u.host, port=u.port or 5432, user="postgres", password=parola) as c:
        kalan = c.execute("SELECT count(*) FROM pg_database WHERE datname LIKE 'yedek_dogrulama_%'").fetchone()[0]
    assert kalan == 0


# --- Otomatik yedek: budama, günlük, durum ----------------------------------

def _sahte_yedek(kok, ad):
    (kok / ad).mkdir(parents=True)
    (kok / ad / MANIFEST).write_text("{}", encoding="utf-8")
    return kok / ad


def test_buda_en_yenileri_tutar_yeni_alinani_ve_yabanci_klasorleri_korur(tmp_path):
    adlar = [f"yedek-202610{g:02d}-183000" for g in range(1, 6)]
    for ad in adlar:
        _sahte_yedek(tmp_path, ad)
    (tmp_path / "yedek-20261001-183000.hatali").mkdir()          # doğrulanamamış: sayılmaz, silinmez
    (tmp_path / "yedek-elle-kopya").mkdir()                       # bu aracın adı değil: dokunulmaz
    silinen = buda(tmp_path, sakla=2, koru=tmp_path / adlar[0])   # en eskisi "az önce alınan" olsa bile korunur
    assert silinen == [adlar[2], adlar[1]]
    assert sorted(p.name for p in tmp_path.iterdir()) == sorted(
        [adlar[0], adlar[3], adlar[4], "yedek-20261001-183000.hatali", "yedek-elle-kopya"])
    with pytest.raises(YedekHatasi):
        buda(tmp_path, sakla=0, koru=tmp_path / adlar[4])


def test_otomatik_basarili_calisma_budar_ve_gunluge_yazar(tmp_path, depolama_kok, monkeypatch):
    kok = tmp_path / "yedekler"
    for g in range(1, 4):
        _sahte_yedek(kok, f"yedek-201901{g:02d}-183000")
    monkeypatch.setattr(ayarlar, "depolama_koku", lambda: depolama_kok)
    # Tam doğrulama ayrı testte sınanıyor; burada akışın kendisi (başarı yolu)
    monkeypatch.setattr(yedek_mod, "dogrula", lambda yol, **_: Dogrulama(
        json.loads((yol / MANIFEST).read_text(encoding="utf-8")), dogrulanan_belge=7))
    kayit = otomatik(kok, sakla=2)
    assert kayit["durum"] == "basarili" and kayit["dogrulanan_belge"] == 7
    assert kayit["silinen"] == ["yedek-20190102-183000", "yedek-20190101-183000"]
    d = durum(kok)
    assert d["son_basarili"]["klasor"] == kayit["klasor"] and d["yedek_sayisi"] == 2


@pytest.mark.skipif(not os.environ.get("AVUKAT_PG_SUPERPW"), reason="AVUKAT_PG_SUPERPW yok")
def test_otomatik_dogrulanamayan_yedegi_ayirir_eskileri_silmez(tmp_path, depolama_kok, monkeypatch):
    # Test anahtarıyla alınan yedekte geliştirme belgelerinin dosyaları yok: tam doğrulama gerçekten başarısız olur
    if not _belge_kaydi_var():
        pytest.skip("Geliştirme veritabanında belge kaydı yok; doğrulama başarısız olmaz.")
    kok = tmp_path / "yedekler"
    eski = _sahte_yedek(kok, "yedek-20190101-183000")
    monkeypatch.setattr(ayarlar, "depolama_koku", lambda: depolama_kok)
    kayit = otomatik(kok, sakla=1)
    assert kayit["durum"] == "hata" and "Doğrulama başarısız" in kayit["mesaj"]
    assert eski.exists()                                          # sağlam eski yedek silinmedi
    assert len(list(kok.glob("yedek-*.hatali"))) == 1 and yedekler(kok) == [eski]
    d = durum(kok)
    assert d["son_deneme"]["durum"] == "hata" and d["son_basarili"] is None


def _belge_kaydi_var() -> bool:
    motor = create_engine(ayarlar.veritabani_url())
    try:
        with motor.connect() as c:
            return c.execute(text("SELECT count(*) FROM belge")).scalar_one() > 0
    finally:
        motor.dispose()


def test_yonetim_yedek_durumu_ve_uyari(tmp_path, monkeypatch, web, buro):  # noqa: F811
    monkeypatch.setattr(ayarlar, "yedek_klasoru", lambda: tmp_path)
    yon = _oturum("yon@ornek.test")
    assert yon.get("/yonetim/yedek").json()["uyari"] is True             # hiç yedek yok
    gunluge_yaz(tmp_path, {"durum": "basarili", "klasor": "yedek-x", "belge_sayisi": 1, "dogrulanan_belge": 1,
                           "silinen": []})
    assert yon.get("/yonetim/yedek").json()["uyari"] is False
    gunluge_yaz(tmp_path, {"durum": "hata", "mesaj": "pg_dump başarısız"})
    d = yon.get("/yonetim/yedek").json()
    assert d["uyari"] is True and d["son_deneme"]["mesaj"] == "pg_dump başarısız"
    assert d["son_basarili"]["klasor"] == "yedek-x"
    assert _oturum("avk@ornek.test").get("/yonetim/yedek").status_code == 403
