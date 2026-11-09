"""Tarih ve tutar kuralları için zor sentetik set. TÜM İÇERİK UYDURMADIR.

İki bölüm vardır:
- GELISTIRME: kurallar iyileştirilirken bakılan set.
- SAKLI: kurallar iyileştirilmeden ÖNCE yazıldı ve iyileştirme sırasında bakılmadı.
  Kuralların genelleşip genelleşmediğini gösterir. Bu sete göre kural ayarlanmaz;
  ayarlanırsa ölçüm anlamını yitirir, yerine yeni bir saklı set yazılmalıdır.

Yalnızca tarih ve tutar işaretlidir (kişi/kurum bu sette değerlendirilmez).

Hedef (bir avukatın görmek isteyeceği) tanımlar:
- Tarih: gün belliyse YYYY-MM-DD; yalnızca ay ve yıl belliyse YYYY-MM; olayın yılı
  "2021 yılında" gibi açıkça belirtilmişse YYYY. Tarih aralığının iki ucu ayrı tarihtir.
  Esas/karar numarasındaki yıl, saat, kanun/madde numarası tarih değildir.
- Tutar: para birimi (TL, lira, Türk lirası, ₺, USD, dolar, EUR, avro, euro) ile
  yazılmış miktar. "bin" ve "milyon" çarpanları uygulanır. Para birimi olmayan sayılar
  (adet, metrekare, yüzde, gün, ay, taksit, sicil/vergi/IBAN numaraları) tutar değildir.
  Yazıyla yazılmış tutar ("beş bin Türk lirası") ayrıca işaretlenir; rakamla da yazıldıysa
  aynı değer bir kez sayılır.
"""

from analiz_seti import Belge, P, T

GELISTIRME = [
    Belge("Gelişim 1 - icra takibi", [[
        "İCRA TAKİP TALEBİ\n\nAlacaklı vekili olarak 2024/5123 Esas sayılı dosyada ",
        P("5.000.-TL", "5000.00 TRY"), " asıl alacak ile ", P("1.250,75.-TL", "1250.75 TRY"),
        " işlemiş faiz talep edilmektedir. Takip ", T("3 Kasım 2024'te", "2024-11-03"), " başlatılmıştır.\n",
        "Borçlu ", T("05/12/2024", "2024-12-05"), " tarihli ödeme emrine itiraz etmemiştir. Ödeme ",
        P("TL 2.500", "2500.00 TRY"), " ve ", P("7.500-TL", "7500.00 TRY"), " olarak iki taksitte yapılacaktır.\n",
        "Vekalet ücreti ", P("17.900,00 TL'dir", "17900.00 TRY"), ". Dosya 14:30'da kalem tarafından kaydedildi.\n",
        "Borçlu vergi no: 4560012345, IBAN: TR12 0006 1005 1978 6457 8413 26",
    ]]),
    Belge("Gelişim 2 - kira ve tazminat", [[
        "Kiracı ", T("2021 yılında", "2021"), " taşınmazı kiralamış, aylık ", P("12.500 lira", "12500.00 TRY"),
        " ödemiştir. ", T("Ocak 2023'ten", "2023-01"), " itibaren kira ", P("18 bin TL", "18000.00 TRY"),
        "'ye çıkarılmıştır.\n",
        "Davacı ", P("1,5 milyon TL", "1500000.00 TRY"), " maddi ve ", P("250 bin lira", "250000.00 TRY"),
        " manevi tazminat talep etmektedir. Taşınmaz 120 m² olup 3 taksit öngörülmüştür.\n",
        "Kira dönemi ", T("01.01.2024", "2024-01-01"), "-", T("31.12.2024", "2024-12-31"), " arasıdır.\n",
        "KDV oranı %20'dir; TBK md. 344 ve 6098 sayılı Kanun uygulanır.",
    ]]),
    Belge("Gelişim 3 - döviz ve yazıyla tutar", [[
        "Sözleşme bedeli ", P("USD 3.000", "3000.00 USD"), " olup, ayrıca ", P("1.200 Avro", "1200.00 EUR"),
        " depozito alınmıştır. Masraf avansı ", P("beş bin Türk lirası", "5000.00 TRY"), " (",
        P("5.000 TL", "5000.00 TRY"), ") olarak yatırılmıştır.\n",
        "Teslim ", T("2.11.24", "2024-11-02"), " tarihinde yapılmış, fatura ", T("15 Mart 2025 Cumartesi", "2025-03-15"),
        " günü kesilmiştir. Toplam 450 adet ürün teslim edilmiştir. Belge 3.11 sürümüyle oluşturulmuştur.",
    ]]),
]

SAKLI = [
    Belge("Saklı 1 - işçilik", [[
        "Davacı işçi ", T("2018 yılının Haziran ayında", "2018-06"), " işe başlamış, ",
        T("28 Şubat 2025'de", "2025-02-28"), " iş akdi feshedilmiştir. Son aylık net ücreti ",
        P("38.750,00.-TL", "38750.00 TRY"), " olup ayrıca ", P("4.000 TL'lik", "4000.00 TRY"),
        " yol yardımı almaktadır.\n",
        "Fazla mesai alacağı için ", P("TRY 64.320,15", "64320.15 TRY"), " talep edilmektedir. Davacı haftada 6 gün, ",
        "günde 11 saat çalışmıştır. Yıllık izin 14 gündür.\n",
        "Tanık 2025/77 Esas sayılı dosyada ", T("10.06.2025", "2025-06-10"), " tarihinde dinlenmiştir.",
    ]]),
    Belge("Saklı 2 - satış ve ceza", [[
        "Alıcı, ", T("Nisan 2024'te", "2024-04"), " ", P("2 milyon 400 bin TL", "2400000.00 TRY"),
        " bedelle taşınmazı satın almış, kapora olarak ", P("₺150.000", "150000.00 TRY"), " ödemiştir.\n",
        "Sözleşmenin 7.3. maddesine göre geç teslimde günlük ", P("2.000,00 TL", "2000.00 TRY"),
        " ceza ödenir. Teslim tarihi ", T("1 Temmuz 2024", "2024-07-01"), " olarak belirlenmiş, ancak teslim ",
        T("15/09/2024", "2024-09-15"), " tarihinde gerçekleşmiştir.\n",
        "Ödemeler ", P("12.000 dolar", "12000.00 USD"), " ve ", P("850 euro", "850.00 EUR"),
        " döviz karşılığı da içerir. Taşınmaz 185 m², arsa payı 1/24'tür.",
    ]]),
    Belge("Saklı 3 - karar özeti", [[
        "Mahkemenin ", T("12.03.2026", "2026-03-12"), " tarihli kararı ile davanın kısmen kabulüne, ",
        P("320.000 TL", "320000.00 TRY"), " alacağın ", T("2019 yılından", "2019"), " itibaren işleyecek ",
        "yasal faiziyle tahsiline, fazlaya ilişkin ", P("80.000-TL", "80000.00 TRY"), "'nin reddine karar verilmiştir.\n",
        "Yargılama giderleri ", P("3.412,60 TL", "3412.60 TRY"), " olup, karar 2026/145 K. sayısıyla ",
        "kesinleşmiştir. Harç ", P("onbin lira", "10000.00 TRY"), " olarak tahsil edilmiştir.\n",
        "Taraflara 2 hafta süre verilmiştir; dosya 4 klasör, 312 sayfadır.",
    ]]),
]
