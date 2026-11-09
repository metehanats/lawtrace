"""Dilekçe çeşitliliği GELİŞTİRME setindeki sonuçları sabitler (gerileme olmasın).

SAKLI set burada test edilmez: testle sabitlenirse kurallar ona göre ayarlanmış olur ve ölçüm
anlamını yitirir. SAKLI yalnızca araclar/dilekce_olcum.py ile ölçülür.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "araclar"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "sentetik_veri"))

from dilekce_cesitlilik import GELISTIRME  # noqa: E402
from dilekce_olcum import olc  # noqa: E402


def test_gelistirme_seti_gerilemez():
    s = olc(GELISTIRME, ayrinti=False)
    assert s["iddia"] == [36, 0, 0]          # doğru, fazla, kaçan
    assert s["delil"] == [51, 0, 0]
    assert s["etiket"] == [26, 35]   # eski saklı setin etiketleri: sözlük genelleşmiyor
    # "Personel dosyası" bilerek açık bırakıldı (taraftaki belge mi, getirtilecek kayıt mı belirsiz)
    assert s["delil_tur"] == [50, 51]
