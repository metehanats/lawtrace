"""Belge dosyalarının diskte şifreli saklanması ve eski dosyaların geçişi. Tüm veriler sentetiktir."""

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import text

from app.belge.depolama import SifreliDepolama, YerelDepolama
from app.belge.sifreleme_gecisi import gecir
from app.belge.yukleme import belge_yukle
from test_belge import docx_uret

ICERIK = b"%PDF-1.7 sentetik dava dilekcesi: Ayse Yilmaz 386.420,50 TL"


@pytest.fixture
def yerel(tmp_path):
    return YerelDepolama(tmp_path)


def test_diskte_sifreli_okurken_cozulur(yerel, tmp_path):
    sifreli = SifreliDepolama(yerel)
    sifreli.kaydet("b/d/1", ICERIK)
    ham = (tmp_path / "b/d/1").read_bytes()
    assert ham.startswith(b"ADT1") and b"Ayse" not in ham and b"%PDF" not in ham
    assert sifreli.oku("b/d/1") == ICERIK
    # Aynı içerik iki kez şifrelenince farklı çıkar (rastgele nonce)
    sifreli.kaydet("b/d/2", ICERIK)
    assert (tmp_path / "b/d/2").read_bytes() != ham


def test_baska_belgenin_yerine_konan_ya_da_bozulan_dosya_cozulmez(yerel, tmp_path):
    sifreli = SifreliDepolama(yerel)
    sifreli.kaydet("b/d/1", ICERIK)
    sifreli.kaydet("b/d/2", b"baska belge")
    (tmp_path / "b/d/2").write_bytes((tmp_path / "b/d/1").read_bytes())
    with pytest.raises(InvalidTag):
        sifreli.oku("b/d/2")
    bozuk = bytearray((tmp_path / "b/d/1").read_bytes())
    bozuk[-1] ^= 1
    (tmp_path / "b/d/1").write_bytes(bytes(bozuk))
    with pytest.raises(InvalidTag):
        sifreli.oku("b/d/1")


def test_sifresiz_dosya_okunmaz(yerel):
    yerel.kaydet("b/d/1", ICERIK)
    with pytest.raises(ValueError, match="şifreli değil"):
        SifreliDepolama(yerel).oku("b/d/1")


def test_gecis_eski_dosyalari_dogrulayarak_sifreler(conn, dava, yerel, tmp_path):
    # Şifreleme öncesi gibi: düz depolamaya yüklenmiş iki belge
    for i in range(2):
        belge_yukle(conn, yerel, dava_id=dava["dava"], kullanici_id=dava["kullanici"],
                    orijinal_ad=f"eski{i}.docx", veri=docx_uret(f"Sentetik eski belge {i}"))
    anahtarlar = conn.execute(text("SELECT depolama_anahtari FROM belge WHERE dava_dosyasi_id = :d "
                                   "ORDER BY orijinal_ad"), {"d": dava["dava"]}).scalars().all()
    duz = {a: yerel.oku(a) for a in anahtarlar}
    # Biri sonradan bozulmuş: özeti tutmaz, dokunulmamalı
    yerel.kaydet(anahtarlar[1], duz[anahtarlar[1]] + b"bozulma")
    (tmp_path / "kayitsiz.bin").write_bytes(b"x")

    deneme = gecir(conn, yerel, deneme=True)
    assert deneme.sifrelenen == 1 and yerel.oku(anahtarlar[0]) == duz[anahtarlar[0]]

    rapor = gecir(conn, yerel)
    assert rapor.sifrelenen == 1 and rapor.ozet_uyusmayan == [anahtarlar[1]] and rapor.kayitsiz_dosya == 1
    assert SifreliDepolama(yerel).oku(anahtarlar[0]) == duz[anahtarlar[0]]
    assert not yerel.oku(anahtarlar[0]).startswith(b"PK")
    assert yerel.oku(anahtarlar[1]).startswith(b"PK")             # bozuk olana dokunulmadı

    # Tekrar çalıştırmak güvenli
    tekrar = gecir(conn, yerel)
    assert (tekrar.sifrelenen, tekrar.zaten_sifreli) == (0, 1)
