"""Dava dosyasının zaman çizelgesi: bulunan tarihlerden olay kronolojisi.

Yorum yapmaz; yalnızca kaynağı doğrulanmış tarih bulgularını sıralar:
- Aynı tarih farklı belgelerde geçiyorsa tek olaydır; tüm kaynakları listelenir.
- Olay adı tarihin yanındaki etikettir ("sözleşme tarihi", "fesih tarihi"). Etiket yoksa
  olay adsızdır; avukat alıntıdan ne olduğunu okur. Ad uydurulmaz.
- Eksik tarih ("Mart 2025", "2024 yılında") kendi döneminin başına sıralanır ve
  hassasiyeti belirtilir; ardışık iki tam tarih arasındaki gün farkı gösterilir.
- Reddedilen bulgu çizelgeye girmez. Açık bir tarih çelişkisinin tarafı olan olay işaretlenir.
"""

from dataclasses import dataclass, field
from datetime import date


@dataclass
class TarihBulgusu:
    id: object
    deger: str                  # YYYY-MM-DD, YYYY-MM ya da YYYY
    ozet: str
    etiket: str | None
    belge_id: object
    belge_adi: str
    sayfa_no: int
    alinti: str
    bas: int | None
    bit: int | None
    dogrulama_durumu: str


@dataclass
class Olay:
    tarih: str
    hassasiyet: str             # gun | ay | yil
    ozet: str
    etiketler: list[str]
    kaynaklar: list[TarihBulgusu]
    onayli: bool                # en az bir kaynak avukatça onaylandı
    celiskili: bool = False
    onceki_olaydan_gun: int | None = None
    celiski_aciklamalari: list[str] = field(default_factory=list)


def hassasiyet(deger: str) -> str:
    return {10: "gun", 7: "ay", 4: "yil"}[len(deger)]


def zaman_cizelgesi(bulgular: list[TarihBulgusu], celiskili: dict | None = None) -> list[Olay]:
    """`celiskili`: açık tarih çelişkisinin tarafı olan bulgu id'si → çelişki açıklaması."""
    celiskili = celiskili or {}
    gruplar: dict[str, list[TarihBulgusu]] = {}
    for b in bulgular:
        if b.dogrulama_durumu != "reddedildi":
            gruplar.setdefault(b.deger, []).append(b)

    olaylar: list[Olay] = []
    onceki_gun: date | None = None
    # "2025-03" < "2025-03-01" < "2025-03-02": eksik tarih döneminin başına düşer
    for deger in sorted(gruplar):
        kaynaklar = sorted(gruplar[deger], key=lambda b: (b.dogrulama_durumu != "onaylandi", b.belge_adi, b.sayfa_no))
        aciklamalar = sorted({celiskili[b.id] for b in kaynaklar if b.id in celiskili})
        olay = Olay(
            tarih=deger,
            hassasiyet=hassasiyet(deger),
            ozet=kaynaklar[0].ozet,
            etiketler=sorted({b.etiket for b in kaynaklar if b.etiket}),
            kaynaklar=kaynaklar,
            onayli=any(b.dogrulama_durumu == "onaylandi" for b in kaynaklar),
            celiskili=bool(aciklamalar),
            celiski_aciklamalari=aciklamalar,
        )
        if olay.hassasiyet == "gun":
            gun = date.fromisoformat(deger)
            if onceki_gun is not None:
                olay.onceki_olaydan_gun = (gun - onceki_gun).days
            onceki_gun = gun
        olaylar.append(olay)
    return olaylar
