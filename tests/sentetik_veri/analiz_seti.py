"""Analiz ölçümü için sentetik dava belgeleri ve beklenen bulgular.

TÜM KİŞİLER, KURUMLAR, TUTARLAR VE OLAYLAR UYDURMADIR.

Belgeler küçük bir yazım kuralıyla kurulur: düz metin parçaları ile işaretli varlıklar
(tür, metindeki yazılış, normalize değer) art arda verilir. Sayfa metni parçaların
birleşimidir; beklenen bulgular işaretli varlıklardan otomatik çıkar. Böylece metin ile
beklenen sonuç birbirinden kopamaz.

Değer biçimleri (analiz modülünün beklediği biçimle aynı):
- tarih: YYYY-MM-DD
- tutar: "<miktar> <para birimi>", ör. "386420.50 TRY" (miktar nokta ondalıklı, 2 hane)
- kisi / kurum: metindeki tam ad

Bilerek konan tuzaklar (bulgu SAYILMAMALI): esas/karar numaraları, T.C. kimlik no,
sayfa numaraları, madde numaraları, yüzde oranları, telefon numaraları.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Varlik:
    tur: str      # tarih | tutar | kisi | kurum
    metin: str    # belgede geçtiği biçim
    deger: str    # normalize değer


def T(metin: str, deger: str) -> Varlik:
    return Varlik("tarih", metin, deger)


def P(metin: str, deger: str) -> Varlik:
    return Varlik("tutar", metin, deger)


def K(metin: str, deger: str | None = None) -> Varlik:
    return Varlik("kisi", metin, deger or metin)


def KR(metin: str, deger: str | None = None) -> Varlik:
    return Varlik("kurum", metin, deger or metin)


@dataclass
class Belge:
    ad: str
    sayfalar: list[list[str | Varlik]]

    def sayfa_metinleri(self) -> list[str]:
        return ["".join(p.metin if isinstance(p, Varlik) else p for p in sayfa) for sayfa in self.sayfalar]

    def beklenen(self) -> dict[tuple[str, str], set[int]]:
        """(tür, değer) -> geçtiği sayfa numaraları. Aynı varlık bir kez sayılır."""
        sonuc: dict[tuple[str, str], set[int]] = {}
        for no, sayfa in enumerate(self.sayfalar, start=1):
            for p in sayfa:
                if isinstance(p, Varlik):
                    sonuc.setdefault((p.tur, p.deger), set()).add(no)
        return sonuc

    def yazilislar(self) -> dict[tuple[str, str], set[str]]:
        """(tür, değer) -> metindeki yazılışları; alıntının varlığı içerip içermediğini denetlemek için."""
        sonuc: dict[tuple[str, str], set[str]] = {}
        for sayfa in self.sayfalar:
            for p in sayfa:
                if isinstance(p, Varlik):
                    sonuc.setdefault((p.tur, p.deger), set()).add(p.metin)
        return sonuc


@dataclass
class Dava:
    ad: str
    belgeler: list[Belge] = field(default_factory=list)


AYSE = K("Ayşe Yılmaz")
CAGLAR = KR("Çağlar Gıda Sanayi ve Ticaret A.Ş.")
MAHKEME = KR("İstanbul 7. Asliye Ticaret Mahkemesi")

DAVA_ALACAK = Dava("Alacak davası", [
    Belge("Dava dilekçesi", [
        [
            "T.C.\n", KR("İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ", "İstanbul 7. Asliye Ticaret Mahkemesi"),
            "'NE\n\nEsas No: 2025/1487\n\nDAVACI: ", AYSE, " (T.C. Kimlik No: 12345678950)\n",
            "VEKİLİ: ", K("Av. Ece Kara", "Ece Kara"), ", İstanbul Barosu sicil no 48213\n",
            "DAVALI: ", CAGLAR, "\n\n",
            "KONU: ", P("386.420,50 TL", "386420.50 TRY"), " alacağın faiziyle birlikte tahsili talebidir.\n\n",
            "AÇIKLAMALAR:\n1. Müvekkil ile davalı şirket arasında ", T("03.11.2024", "2024-11-03"),
            " tarihinde mal satış sözleşmesi imzalanmıştır.\n",
            "2. Müvekkil sözleşme konusu malları ", T("15 Kasım 2024", "2024-11-15"),
            " tarihinde eksiksiz teslim etmiştir.\n",
        ],
        [
            "3. Davalıya ", T("17.02.2025", "2025-02-17"), " tarihinde ", KR("Beyoğlu 12. Noterliği"),
            " aracılığıyla ihtarname gönderilmiş, ancak ödeme yapılmamıştır.\n",
            "4. Davalı şirket yetkilisi ", K("Kemal Çağlar"), ", ", T("12 Mart 2025", "2025-03-12"),
            " tarihli yazısıyla borcun ", P("120.000 TL", "120000.00 TRY"), "'lik kısmını kabul etmiştir.\n",
            "5. Sözleşmenin 4.2. maddesi uyarınca gecikme halinde ", P("50.000,00 TL", "50000.00 TRY"),
            " cezai şart öngörülmüştür. Yıllık faiz oranı %24,5'tir.\n\n",
            "DELİLLER: Sözleşme, teslim tutanağı, ihtarname, tanık ", K("Hüseyin Aksoy"), " beyanı.\n\n",
            "SONUÇ VE İSTEM: ", P("386.420,50 TL", "386420.50 TRY"),
            "'nin dava tarihinden itibaren faiziyle tahsiline karar verilmesini arz ederiz.\n\nSayfa 2/2",
        ],
    ]),
    Belge("Bilirkişi raporu", [
        [
            "BİLİRKİŞİ RAPORU\n\nDosya: ", MAHKEME, " 2025/1487 Esas\n",
            "Bilirkişi: ", K("Dr. Selma Koç", "Selma Koç"), " (Mali Müşavir)\n",
            "Rapor tarihi: ", T("21.06.2025", "2025-06-21"), "\n\n",
            "İncelenen faturalar:\n",
            "- ", T("03.11.2024", "2024-11-03"), " tarihli fatura: ", P("120.000,00 TL", "120000.00 TRY"), "\n",
            "- ", T("02.12.2024", "2024-12-02"), " tarihli fatura: ", P("214.300,50 TL", "214300.50 TRY"), "\n",
            "- ", T("07.01.2025", "2025-01-07"), " tarihli fatura: ", P("52.120,00 TL", "52120.00 TRY"), "\n",
        ],
        [
            "Davalı ", CAGLAR, " tarafından bu faturalara karşılık herhangi bir ödeme yapıldığına dair kayda ",
            "rastlanmamıştır. Banka kayıtları ", KR("Örnekbank A.Ş."), "'den celp edilmiştir.\n\n",
            "SONUÇ: Faturaların toplamı ", P("386.420,50 TL", "386420.50 TRY"),
            " olup, davacı ", AYSE, " bu tutarı talep edebilir.\n",
            "Tel: 0212 555 01 23 · Sayfa 2",
        ],
    ]),
])

DAVA_IS = Dava("İşçilik alacağı", [
    Belge("İhtarname", [
        [
            "İHTARNAME\n\nKeşideci: ", K("Murat Demirci"), "\n",
            "Vekili: ", K("Av. Zeynep Aydın", "Zeynep Aydın"), "\n",
            "Muhatap: ", KR("Kuzey Lojistik Ltd. Şti."), "\n\n",
            "Müvekkilim ", T("1 Şubat 2019", "2019-02-01"), " tarihinden ", T("30 Nisan 2025", "2025-04-30"),
            " tarihine kadar şirketinizde forklift operatörü olarak çalışmış, iş akdi haklı bir neden ",
            "olmaksızın feshedilmiştir. Son brüt ücreti aylık ", P("42.500 TL", "42500.00 TRY"), "'dir.\n\n",
            "Ödenmeyen kıdem tazminatı ", P("268.750,00 TL", "268750.00 TRY"), ", ihbar tazminatı ",
            P("63.750,00 TL", "63750.00 TRY"), " ve 14 günlük yıllık izin ücreti ",
            P("19.833,33 TL", "19833.33 TRY"), " tutarındadır.\n\n",
            "İşbu ihtarnamenin tebliğinden itibaren 7 gün içinde toplam ", P("352.333,33 TL", "352333.33 TRY"),
            "'nin ödenmesini, aksi halde ", KR("Ankara Batı İş Mahkemesi"), "'nde dava açılacağını ihtar ederim.\n",
            "Tarih: ", T("09.05.2025", "2025-05-09"),
        ],
    ]),
    Belge("Tanık beyanı tutanağı", [
        [
            "TANIK BEYANI\n\nTanık ", K("Gökhan Sarı"), " beyanında: Davacı ", K("Murat Demirci"),
            " ile ", T("2020 yılının Mart ayında", "2020-03"), " birlikte çalışmaya başladık. Davacı genellikle ",
            "hafta sonları da çalışırdı. İşten çıkarıldığı gün, yani ", T("30 Nisan 2025", "2025-04-30"),
            ", şube müdürü ", K("Levent Tekin"), " kendisine artık gelmemesini söyledi. Bildiğim kadarıyla ",
            "maaşı ", P("42.500 TL", "42500.00 TRY"), " idi, bazen ", P("5.000 TL", "5000.00 TRY"),
            " prim alırdı.\n\nBeyan tarihi: ", T("14.10.2025", "2025-10-14"), " · Dosya no 2025/388",
        ],
    ]),
])

DAVA_KIRA = Dava("Kira tespit", [
    Belge("Kira sözleşmesi", [
        [
            "KİRA SÖZLEŞMESİ\n\nKiraya veren: ", K("Hatice Özdemir"), " (T.C. 23456789012)\n",
            "Kiracı: ", KR("Ege Kırtasiye ve Yayıncılık Ltd. Şti."), "\n",
            "Kiralanan: Kadıköy, Moda Cad. No: 41 dükkan\n",
            "Başlangıç tarihi: ", T("01.09.2021", "2021-09-01"), "\nSüre: 5 yıl\n",
            "Aylık kira bedeli: ", P("18.000 TL (onsekizbin Türk Lirası)", "18000.00 TRY"), "\n",
            "Depozito: ", P("$2,000", "2000.00 USD"), "\n",
            "Kira her ayın 5'inde ödenir. Madde 7: Yıllık artış TÜFE oranında yapılır.\n",
        ],
    ]),
    Belge("Dava dilekçesi (kira tespit)", [
        [
            KR("İSTANBUL ANADOLU 3. SULH HUKUK MAHKEMESİ", "İstanbul Anadolu 3. Sulh Hukuk Mahkemesi"),
            "'NE\n\nDavacı: ", K("Hatice Özdemir"), "\nDavalı: ", KR("Ege Kırtasiye ve Yayıncılık Ltd. Şti."),
            "\n\nDavalı ", T("01.09.2021", "2021-09-01"), " tarihli sözleşme ile dükkanı kiralamış, ",
            "güncel kira bedeli ", P("29.400 TL", "29400.00 TRY"), "'dir. Emsal dükkanların kirası ise ",
            P("65.000 TL", "65000.00 TRY"), " civarındadır. Bilirkişi incelemesi sonucu ",
            "kira bedelinin ", T("1 Eylül 2026", "2026-09-01"), " tarihinden geçerli olmak üzere tespitini talep ederiz.\n",
        ],
    ]),
])

DAVALAR = [DAVA_ALACAK, DAVA_IS, DAVA_KIRA]
