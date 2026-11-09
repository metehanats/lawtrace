"""OCR ön işleme testleri (veritabanı gerektirmez)."""

import numpy as np
from PIL import Image, ImageDraw

from app.belge import on_isleme
from test_ocr import taranmis_sayfa

SATIRLAR = [f"Sentetik satır {i}: Ödeme tutarı {i}.000 TL" for i in range(1, 15)]


def test_egiklik_acisi_bulunur():
    sayfa = taranmis_sayfa(SATIRLAR)
    for aci in (-3.0, 1.5, 4.0):
        egik = sayfa.rotate(aci, resample=Image.BICUBIC, fillcolor=255)
        # Bulunan açı, eğikliği geri alacak açıdır
        assert abs(on_isleme.egiklik_acisi(egik) + aci) <= 0.3, aci


def test_duz_sayfa_dondurulmez():
    sayfa = taranmis_sayfa(SATIRLAR)
    assert on_isleme.egiklik_duzelt(sayfa) is sayfa


def test_arka_plan_golgesi_giderilir():
    sayfa = np.asarray(taranmis_sayfa(SATIRLAR), dtype=np.float32)
    golgeli = Image.fromarray((sayfa * np.linspace(1.0, 0.45, sayfa.shape[1])[None, :]).astype(np.uint8))
    duz = np.asarray(on_isleme.arka_plan_duzelt(golgeli))
    # Gölgeli kenardaki boş kâğıt yeniden beyaza yakın olur, mürekkep koyu kalır
    assert np.asarray(golgeli)[3000:, -300:].mean() < 130
    assert duz[3000:, -300:].mean() > 240
    assert duz.min() < 60


def test_tum_yontemler_boyutu_korur():
    sayfa = taranmis_sayfa(SATIRLAR).rotate(2, fillcolor=255)
    for ad in on_isleme.YONTEMLER:
        sonuc = on_isleme.isle(ad, sayfa).goruntu
        assert sonuc.size == sayfa.size and sonuc.mode == "L", ad


def test_bos_sayfa_hata_vermez():
    for renk in (255, 0, 128):
        bos = Image.new("L", (2480, 3508), color=renk)
        for ad in on_isleme.YONTEMLER:
            assert on_isleme.isle(ad, bos).goruntu.size == bos.size, (ad, renk)


def _cizgili_sayfa():
    sayfa = taranmis_sayfa(SATIRLAR[:3])
    cizim = ImageDraw.Draw(sayfa)
    cizim.line([(200, 1000), (2200, 1000)], fill=0, width=3)   # yatay
    cizim.line([(1200, 900), (1200, 1600)], fill=0, width=3)   # dikey
    return sayfa


def test_cizgiler_silinir_metin_kalir():
    sayfa = _cizgili_sayfa()
    temiz, dikey = on_isleme.cizgi_sil(sayfa)
    a = np.asarray(temiz)
    assert a[995:1005, 300:2100].min() > 200      # yatay çizgi gitti
    assert a[950:1550, 1195:1205].min() > 200     # dikey çizgi gitti
    assert a[300:700, 200:1500].min() < 60        # metin duruyor
    assert dikey is not None and dikey[1200, 1200] and not dikey[1000, 500]


def test_dikey_cizgi_sorgusu():
    islenmis = on_isleme.OnIslenmis(*on_isleme.cizgi_sil(_cizgili_sayfa()))
    assert islenmis.dikey_cizgi_var(1150, 1250, 1100, 1300)
    assert not islenmis.dikey_cizgi_var(1300, 1500, 1100, 1300)
    assert not islenmis.dikey_cizgi_var(1150, 1250, 2000, 2500)
    assert not on_isleme.OnIslenmis(Image.new("L", (10, 10), 255)).dikey_cizgi_var(0, 10, 0, 10)
