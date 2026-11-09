"""Özel nitelikli kişisel veri (KVKK md. 6) içerebilecek belgelerin tespiti.

Tutucu (fazla işaretlemeye yatkın) bir anahtar kelime taramasıdır: işaretlenen belge
avukatın ayrıca onayı olmadan analize gönderilmez. Kaçırılan belgeyi avukat elle
işaretleyebilir. Bu bir sınıflandırıcı değil, bir emniyet kapısıdır.
"""

import re

from app.analiz.cikarim import tr_kucuk

ANAHTAR_KELIMELER = {
    "sağlık": [
        "teşhis", "tanısı", "tanı:", "epikriz", "sağlık raporu", "sağlık kurulu", "hastane", "ameliyat",
        "reçete", "psikiyatri", "engellilik oranı", "maluliyet", "tıbbi", "hasta dosyası", "adli tıp",
    ],
    "ceza mahkûmiyeti / güvenlik tedbiri": [
        "adli sicil", "sabıka", "mahkûmiyet", "mahkumiyet", "hapis cezası",
        "hükmün açıklanmasının geri bırakılması", "ceza infaz", "tutuklu", "tutuklama", "sanık",
    ],
    "din / inanç": ["dini inanc", "mezhebi", "mezhep"],
    "sendika üyeliği": ["sendika üyeliği", "sendikaya üye"],
    "biyometrik / genetik": ["parmak izi", "dna", "genetik", "biyometrik"],
    "cinsel hayat": ["cinsel hayat", "cinsel yönelim"],
}

_KALIPLAR = {
    alan: re.compile(r"(?<![a-zçğıöşü])(" + "|".join(re.escape(k) for k in kelimeler) + ")")
    for alan, kelimeler in ANAHTAR_KELIMELER.items()
}


def tespit_et(metinler: list[str]) -> str | None:
    """Özel nitelikli veri işareti varsa kısa bir neden ("sağlık: epikriz, hastane"), yoksa None."""
    metin = tr_kucuk("\n".join(metinler))
    nedenler = []
    for alan, kalip in _KALIPLAR.items():
        bulunan = sorted({m.group(1) for m in kalip.finditer(metin)})
        if bulunan:
            nedenler.append(f"{alan}: {', '.join(bulunan[:3])}")
    return "; ".join(nedenler) or None
