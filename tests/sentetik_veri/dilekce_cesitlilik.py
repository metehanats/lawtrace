"""Dilekçe yazım çeşitliliği seti: bölüm başlıkları, numaralandırma ve etiket ifadeleri.
TÜM İÇERİK UYDURMADIR (kişi, kurum, tutar, tarih, dosya no).

Ölçülen üç şey:
1. İddialar: olay/açıklama/savunma bölümündeki her paragraf (numaralıysa her madde) bir iddiadır.
   Beklenen değer, iddianın başındaki ilk birkaç sözcüktür (numara hariç).
2. Delil kalemleri: delil bölümündeki her kalem ve türü. Dosyaya hiç belge yüklenmemiş sayılır;
   bu yüzden belge olması gereken kalemin beklenen türü "eksik"tir. "belge_disi": tanık, keşif,
   bilirkişi, yemin, "her türlü delil"; "dis_kaynak": başka yerden getirtilecek dosya ya da kayıt.
3. Etiketler: değerin (tarih/tutar) yanındaki, tek değeri olması beklenen etiket (çelişki tespiti
   bunlara bakar). Beklenen None ise değer etiketsiz kalmalıdır (fatura, ödeme gibi tekrarlanabilir).

İki bölüm:
- GELISTIRME: kurallar iyileştirilirken bakılır.
- SAKLI: kurallar iyileştirilmeden ÖNCE yazıldı, iyileştirme sırasında bakılmaz. Kurallar bu sete
  göre ayarlanırsa ölçüm anlamını yitirir; o zaman yeni bir saklı set yazılmalıdır.

2026-11-01: İlk saklı set iki hata gösterdi ("fotoğraflar" kalemi, "AÇIKLAMALARIMIZ" başlığı).
Bunlar düzeltileceği için o set artık görülmüş sayılır: ESKI_SAKLI adıyla geliştirmeye katıldı.
Yeni SAKLI, düzeltmelerden ÖNCE yazıldı.

Sınır: iki bölümü de aynı kişi (Claude) yazdı; gerçek dilekçelerin çeşitliliğini tam temsil
etmeyebilir. Gerçek kullanımdan önce avukatın gördüğü biçimlerle genişletilmelidir.
"""

from dataclasses import dataclass, field


@dataclass
class Dilekce:
    ad: str
    metin: str
    iddialar: list[str] = field(default_factory=list)                 # iddia başları, sırayla
    deliller: list[tuple[str, str]] = field(default_factory=list)     # (kalem başı, tür)
    etiketler: list[tuple[str, str, str | None]] = field(default_factory=list)  # (değer metni, tür, etiket)


GELISTIRME = [
    Dilekce(
        "Gelişim 1 - alacak, Romen rakamlı başlıklar",
        "ANKARA ( ) ASLİYE TİCARET MAHKEMESİ'NE\n\n"
        "DAVACI : Orman Kereste Ltd. Şti.\nDAVALI : Kaya Yapı A.Ş.\n"
        "DAVA DEĞERİ : 245.000,00 TL\n\n"
        "I- OLAYLAR :\n"
        "1- Müvekkil şirket ile davalı arasında 14.02.2024 tarihinde kereste tedarik sözleşmesi akdedilmiştir.\n"
        "2- Müvekkil, sözleşme gereği malları eksiksiz teslim etmiş ve faturalarını düzenlemiştir.\n"
        "3- Davalı, 01.04.2024 tarihli ihtarnameye rağmen bakiye borcunu ödememiştir.\n\n"
        "II- HUKUKİ NEDENLER : TBK, TTK ve ilgili mevzuat.\n\n"
        "III- DELİLLER :\n"
        "1. Tedarik sözleşmesi\n2. Faturalar\n3. Ticari defterler üzerinde bilirkişi incelemesi\n4. Tanık beyanları\n\n"
        "IV- NETİCE-İ TALEP : Davanın kabulüne karar verilmesini arz ederiz.",
        iddialar=["Müvekkil şirket ile davalı", "Müvekkil, sözleşme gereği", "Davalı, 01.04.2024"],
        deliller=[("Tedarik sözleşmesi", "eksik"), ("Faturalar", "eksik"),
                  ("Ticari defterler üzerinde bilirkişi", "belge_disi"), ("Tanık beyanları", "belge_disi")],
        etiketler=[("245.000,00 TL", "tutar", "dava değeri"), ("14.02.2024", "tarih", "sözleşme tarihi"),
                   ("01.04.2024", "tarih", "ihtarname tarihi")],
    ),
    Dilekce(
        "Gelişim 2 - cevap, harfli maddeler",
        "İSTANBUL 12. İŞ MAHKEMESİ'NE\n\nDOSYA NO : 2025/321 Esas\nCEVAP VEREN DAVALI : Mavi Lojistik A.Ş.\n\n"
        "USULE İLİŞKİN İTİRAZLARIMIZ :\n"
        "a) Davacının arabuluculuk son tutanağı dosyaya sunulmamıştır.\n\n"
        "ESASA İLİŞKİN CEVAPLARIMIZ :\n"
        "a) Davacı, işe giriş tarihi olarak 03.05.2019 tarihini bildirmiş ise de SGK kayıtları farklıdır.\n"
        "b) Davacının iş akdi 15.01.2025 tarihinde devamsızlık nedeniyle haklı olarak feshedilmiştir.\n"
        "c) Davacının son brüt ücreti 28.500,00 TL olup fazlası talep edilemez.\n\n"
        "DELİLLERİMİZ : Personel dosyası, SGK kayıtları, devam çizelgeleri, tanık ve her türlü yasal delil.\n\n"
        "SONUÇ VE TALEP : Davanın reddine karar verilmesini saygıyla arz ederiz.",
        iddialar=["Davacının arabuluculuk son", "Davacı, işe giriş tarihi", "Davacının iş akdi",
                  "Davacının son brüt ücreti"],
        deliller=[("Personel dosyası", "eksik"), ("SGK kayıtları", "dis_kaynak"),
                  ("devam çizelgeleri", "eksik"), ("tanık", "belge_disi"), ("her türlü yasal delil", "belge_disi")],
        etiketler=[("03.05.2019", "tarih", "işe başlama tarihi"), ("15.01.2025", "tarih", "fesih tarihi"),
                   ("28.500,00 TL", "tutar", "son ücret")],
    ),
    Dilekce(
        "Gelişim 3 - işçilik alacağı, numarasız paragraflar",
        "ANTALYA İŞ MAHKEMESİ'NE\n\nDAVACI : Selin Aydın\nDAVALI : Deniz Otelcilik A.Ş.\n"
        "KONU : Kıdem ve ihbar tazminatı ile fazla mesai alacağı talebidir.\n\n"
        "AÇIKLAMALAR :\n"
        "Müvekkil davalı işyerinde 01.06.2018 tarihinde çalışmaya başlamış, en son aylık net 31.000,00 TL\n"
        "ücretle resepsiyon şefi olarak görev yapmıştır.\n\n"
        "Müvekkilin iş sözleşmesi 30.09.2024 tarihinde işveren tarafından haklı neden olmaksızın feshedilmiştir.\n\n"
        "Müvekkil haftada ortalama 15 saat fazla çalışma yapmış, bunun karşılığı ödenmemiştir.\n\n"
        "HUKUKİ SEBEPLER : 4857 sayılı İş Kanunu.\n\n"
        "HUKUKİ DELİLLER : Bordrolar, SGK hizmet dökümü, puantaj kayıtları, tanık beyanları, bilirkişi incelemesi.\n\n"
        "SONUÇ VE İSTEM : Fazlaya ilişkin haklarımız saklı kalmak kaydıyla 10.000,00 TL kıdem tazminatının "
        "faiziyle tahsiline karar verilmesini arz ederiz.",
        iddialar=["Müvekkil davalı işyerinde", "Müvekkilin iş sözleşmesi", "Müvekkil haftada ortalama"],
        deliller=[("Bordrolar", "eksik"), ("SGK hizmet dökümü", "dis_kaynak"), ("puantaj kayıtları", "dis_kaynak"),
                  ("tanık beyanları", "belge_disi"), ("bilirkişi incelemesi", "belge_disi")],
        etiketler=[("01.06.2018", "tarih", "işe başlama tarihi"), ("31.000,00 TL", "tutar", "son ücret"),
                   ("30.09.2024", "tarih", "fesih tarihi"), ("10.000,00 TL", "tutar", "kıdem tazminatı")],
    ),
    Dilekce(
        "Gelişim 4 - tahliye, maddi vakıalar",
        "İZMİR ( ) SULH HUKUK MAHKEMESİ'NE\n\nDAVACI : Hasan Yurt\nDAVALI : Ece Kılıç\n"
        "DAVA : Kira bedelinin ödenmemesi nedeniyle tahliye\n\n"
        "MADDİ VAKIALAR :\n"
        "1) Taraflar arasında 01.03.2022 başlangıç tarihli kira sözleşmesi bulunmaktadır.\n"
        "2) Aylık kira bedeli 15.000 TL olup davalı Ocak ve Şubat 2025 kiralarını ödememiştir.\n"
        "3) Davalıya 10.03.2025 tarihinde ihtarname tebliğ edilmiş, otuz günlük süre geçmiştir.\n\n"
        "DELİLLER : Kira sözleşmesi (Ek-1), ihtarname ve tebliğ şerhi (Ek-2), tapu kaydı, banka kayıtları.\n\n"
        "TALEP SONUCU : Davalının taşınmazdan tahliyesine karar verilmesini arz ederim.",
        iddialar=["Taraflar arasında 01.03.2022", "Aylık kira bedeli", "Davalıya 10.03.2025"],
        deliller=[("Kira sözleşmesi", "eksik"), ("ihtarname ve tebliğ şerhi", "eksik"), ("tapu kaydı", "dis_kaynak"),
                  ("banka kayıtları", "dis_kaynak")],
        # Kira bedeli yıldan yıla artabilir: tek değerli sayılmaz (çelişki üretmesin)
        etiketler=[("01.03.2022", "tarih", "kira başlangıç tarihi"), ("15.000 TL", "tutar", None),
                   ("10.03.2025", "tarih", "tebliğ tarihi")],
    ),
    Dilekce(
        "Gelişim 5 - itirazın iptali, izahat",
        "KONYA ( ) ASLİYE HUKUK MAHKEMESİ'NE\n\nDAVACI : Güneş Tarım Kooperatifi\nDAVALI : Ali Er\n"
        "HARCA ESAS DEĞER : 86.400,00 TL\n\n"
        "İZAHAT :\n"
        "1. Müvekkil kooperatif, davalıya 2024 yılında gübre ve tohum satmıştır.\n"
        "2. Ödenmeyen bakiye için Konya 4. İcra Dairesi'nin 2025/1550 Esas sayılı dosyasıyla takip başlatılmıştır.\n"
        "3. Davalı borca haksız olarak itiraz etmiştir. 05.02.2025 tarihli fatura ve 12.02.2025 tarihli fatura "
        "dosyaya sunulmuştur.\n\n"
        "DELİLLER VE EKLER : Faturalar, cari hesap ekstresi, Konya 4. İcra Dairesi'nin 2025/1550 Esas sayılı dosyası.\n\n"
        "SONUÇ VE İSTEM : İtirazın iptaline ve %20 icra inkar tazminatına karar verilmesini arz ederiz.",
        iddialar=["Müvekkil kooperatif, davalıya", "Ödenmeyen bakiye için", "Davalı borca haksız"],
        deliller=[("Faturalar", "eksik"), ("cari hesap ekstresi", "eksik"),
                  ("Konya 4. İcra Dairesi'nin 2025/1550", "dis_kaynak")],
        etiketler=[("86.400,00 TL", "tutar", "dava değeri"), ("05.02.2025", "tarih", None),
                   ("12.02.2025", "tarih", None)],
    ),
    Dilekce(
        "Gelişim 6 - tazminat, talep miktarı",
        "BURSA ( ) ASLİYE HUKUK MAHKEMESİ'NE\n\nDAVACI : Mert Şahin\nDAVALI : Hızlı Taşımacılık Ltd. Şti.\n\n"
        "AÇIKLAMALAR\n"
        "1 - Müvekkil 07.08.2024 günü davalıya ait aracın çarpması sonucu yaralanmıştır.\n"
        "2 - Kaza tespit tutanağında davalı sürücü tam kusurlu bulunmuştur.\n"
        "3 - Müvekkilin tedavi giderleri ve iş göremezlik zararı için talep miktarı 120.000,00 TL'dir.\n\n"
        "DELİLLER\n"
        "- Kaza tespit tutanağı\n- Hastane kayıtları\n- Adli tıp raporu\n- Bilirkişi incelemesi\n\n"
        "SONUÇ VE İSTEM\nFazlaya ilişkin haklar saklı kalmak kaydıyla tazminatın tahsilini arz ederiz.",
        iddialar=["Müvekkil 07.08.2024 günü", "Kaza tespit tutanağında", "Müvekkilin tedavi giderleri"],
        deliller=[("Kaza tespit tutanağı", "eksik"), ("Hastane kayıtları", "dis_kaynak"), ("Adli tıp raporu", "eksik"),
                  ("Bilirkişi incelemesi", "belge_disi")],
        etiketler=[("07.08.2024", "tarih", "olay tarihi"), ("120.000,00 TL", "tutar", "talep edilen toplam")],
    ),
]

ESKI_SAKLI = [
    Dilekce(
        "Saklı 1 - olayların özeti, delil listesi",
        "ESKİŞEHİR ( ) ASLİYE TİCARET MAHKEMESİ'NE\n\nDAVACI : Yıldız Ambalaj A.Ş.\nDAVALI : Ova Gıda Ltd. Şti.\n"
        "DAVA DEĞERİ : 312.750,00 TL\n\n"
        "OLAYLARIN ÖZETİ :\n"
        "1. Taraflar arasında 20.06.2023 tarihinde ambalaj malzemesi satım sözleşmesi imzalanmıştır.\n"
        "2. Müvekkil teslimatları zamanında yapmış, davalı 312.750,00 TL tutarındaki bakiyeyi ödememiştir.\n"
        "3. Davalıya gönderilen ihtarname 02.12.2024 tarihinde tebliğ edilmiştir.\n\n"
        "DELİL LİSTESİ :\n"
        "Ek 1 – Satım sözleşmesi\nEk 2 – Sevk irsaliyeleri\nEk 3 – İhtarname\nTanık: Sevgi Uçar\n\n"
        "NETİCE VE İSTEM : Davanın kabulünü arz ederiz.",
        iddialar=["Taraflar arasında 20.06.2023", "Müvekkil teslimatları zamanında", "Davalıya gönderilen ihtarname"],
        deliller=[("Ek 1 – Satım sözleşmesi", "eksik"), ("Ek 2 – Sevk irsaliyeleri", "eksik"),
                  ("Ek 3 – İhtarname", "eksik"), ("Tanık: Sevgi Uçar", "belge_disi")],
        etiketler=[("20.06.2023", "tarih", "sözleşme tarihi"), ("02.12.2024", "tarih", "tebliğ tarihi")],
    ),
    Dilekce(
        "Saklı 2 - cevap, savunmalarımız ve küçük harfli başlıklar",
        "Ankara 5. Tüketici Mahkemesi'ne\n\nDosya No: 2025/88 Esas\nDavalı: Parlak Mobilya Ltd. Şti.\n\n"
        "Savunmalarımız:\n"
        "1. Davacı, 11.11.2024 tarihli satış sözleşmesi ile 48.900,00 TL bedelli mobilya takımı satın almıştır.\n"
        "2. Ürünler 25.11.2024 tarihinde eksiksiz teslim edilmiş, teslim tutanağı imzalanmıştır.\n"
        "3. Davacının ayıp iddiası, kullanım hatasından kaynaklanmaktadır.\n\n"
        "Delillerimiz: Satış sözleşmesi, teslim tutanağı, fotoğraflar, keşif ve bilirkişi incelemesi.\n\n"
        "Sonuç ve Talep: Davanın reddine karar verilmesini arz ederiz.",
        iddialar=["Davacı, 11.11.2024 tarihli", "Ürünler 25.11.2024 tarihinde", "Davacının ayıp iddiası"],
        deliller=[("Satış sözleşmesi", "eksik"), ("teslim tutanağı", "eksik"), ("fotoğraflar", "eksik"),
                  ("keşif", "belge_disi"), ("bilirkişi incelemesi", "belge_disi")],
        etiketler=[("11.11.2024", "tarih", "sözleşme tarihi"), ("48.900,00 TL", "tutar", "satış bedeli"),
                   ("25.11.2024", "tarih", "teslim tarihi")],
    ),
    Dilekce(
        "Saklı 3 - işçi, açıklamalarımız",
        "GAZİANTEP ( ) İŞ MAHKEMESİ'NE\n\nDAVACI : Burak Tan\nDAVALI : Tekstil Sanayi A.Ş.\n\n"
        "AÇIKLAMALARIMIZ :\n"
        "1. Müvekkil 12.09.2016 tarihinden itibaren davalı işyerinde makine operatörü olarak çalışmıştır.\n"
        "2. Müvekkilin son brüt maaşı 34.200,00 TL'dir.\n"
        "3. İş akdi 28.02.2025 tarihinde işverence feshedilmiş, müvekkilin çıkış kodu hatalı bildirilmiştir.\n\n"
        "DELİLLER : SGK kayıtları, işyeri şahsi sicil dosyası, maaş bordroları, tanıklar, yemin.\n\n"
        "NETİCE-İ TALEP : Kıdem tazminatı ile ihbar tazminatının tahsilini arz ederiz.",
        iddialar=["Müvekkil 12.09.2016 tarihinden", "Müvekkilin son brüt maaşı", "İş akdi 28.02.2025"],
        deliller=[("SGK kayıtları", "dis_kaynak"), ("işyeri şahsi sicil dosyası", "dis_kaynak"),
                  ("maaş bordroları", "eksik"), ("tanıklar", "belge_disi"), ("yemin", "belge_disi")],
        etiketler=[("12.09.2016", "tarih", "işe başlama tarihi"), ("34.200,00 TL", "tutar", "son ücret"),
                   ("28.02.2025", "tarih", "fesih tarihi")],
    ),
    Dilekce(
        "Saklı 4 - kira, olaylar ve harç değeri",
        "İSTANBUL ANADOLU ( ) SULH HUKUK MAHKEMESİ'NE\n\nDAVACI : Nur Ateş\nDAVALI : Kemal Öz\n"
        "HARÇ DEĞERİ : 21.600,00 TL\n\n"
        "OLAYLAR :\n"
        "a) Davalı, 15.04.2021 başlangıçlı kira sözleşmesiyle müvekkilin dairesinde kiracıdır.\n"
        "b) Aylık kira bedeli 18.000,00 TL'dir; davalı iki kira dönemini ödememiştir.\n"
        "c) Davalıya 03.01.2025 tarihinde ihtarname keşide edilmiştir.\n\n"
        "DELİLLER : Kira kontratı, ihtarname, banka dekontları ve sair deliller.\n\n"
        "SONUÇ VE İSTEM : Tahliyeye karar verilmesini arz ederim.",
        iddialar=["Davalı, 15.04.2021 başlangıçlı", "Aylık kira bedeli", "Davalıya 03.01.2025"],
        deliller=[("Kira kontratı", "eksik"), ("ihtarname", "eksik"), ("banka dekontları", "eksik"),
                  ("sair deliller", "belge_disi")],
        etiketler=[("21.600,00 TL", "tutar", "dava değeri"), ("15.04.2021", "tarih", "kira başlangıç tarihi"),
                   ("18.000,00 TL", "tutar", None), ("03.01.2025", "tarih", "ihtarname tarihi")],
    ),
    Dilekce(
        "Saklı 5 - tazminat, numarasız ve bölünmüş satırlar",
        "MERSİN ( ) ASLİYE HUKUK MAHKEMESİ'NE\n\nDAVACI : Okan Yel\nDAVALI : Sigorta A.Ş.\n\n"
        "AÇIKLAMALAR :\n"
        "Müvekkilin aracı 19.10.2024 tarihinde davalı şirkete kasko sigortalı iken\n"
        "sel nedeniyle hasar görmüştür.\n\n"
        "Davalı şirket, hasar ihbarına rağmen 6 aydır ödeme yapmamıştır. Eksper raporunda\n"
        "hasar bedeli 96.000,00 TL olarak belirlenmiştir.\n\n"
        "DELİLLER : Kasko poliçesi, eksper raporu, hasar dosyası, fotoğraflar, bilirkişi.\n\n"
        "SONUÇ VE İSTEM : Hasar bedelinin tahsilini arz ederiz.",
        iddialar=["Müvekkilin aracı 19.10.2024", "Davalı şirket, hasar ihbarına"],
        deliller=[("Kasko poliçesi", "eksik"), ("eksper raporu", "eksik"), ("hasar dosyası", "dis_kaynak"),
                  ("fotoğraflar", "eksik"), ("bilirkişi", "belge_disi")],
        etiketler=[("19.10.2024", "tarih", "olay tarihi"), ("96.000,00 TL", "tutar", "hasar bedeli")],
    ),
    Dilekce(
        "Saklı 6 - cevap, esasa ilişkin savunmalar ve ödeme tarihleri",
        "KAYSERİ ( ) ASLİYE TİCARET MAHKEMESİ'NE\n\nDosya: 2025/412 E.\n\n"
        "ESASA İLİŞKİN SAVUNMALARIMIZ :\n"
        "1- Müvekkil şirket, davacıya 10.01.2025 tarihinde 40.000,00 TL ödeme yapmıştır.\n"
        "2- Müvekkil şirket ayrıca 10.02.2025 tarihinde 40.000,00 TL daha ödemiştir.\n"
        "3- Davacının talep ettiği 150.000,00 TL'lik alacak, bu ödemeler düşülmeden hesaplanmıştır.\n\n"
        "DELİLLER : Banka dekontları, cari hesap mutabakatı, ticari defterler.\n\n"
        "SONUÇ : Davanın reddini talep ederiz.",
        iddialar=["Müvekkil şirket, davacıya", "Müvekkil şirket ayrıca", "Davacının talep ettiği"],
        deliller=[("Banka dekontları", "eksik"), ("cari hesap mutabakatı", "eksik"), ("ticari defterler", "eksik")],
        etiketler=[("10.01.2025", "tarih", None), ("10.02.2025", "tarih", None),
                   ("150.000,00 TL", "tutar", "talep edilen toplam")],
    ),
]

GELISTIRME = GELISTIRME + ESKI_SAKLI


SAKLI = [
    Dilekce(
        "Yeni saklı 1 - parantezli numaralar, tireli delil listesi",
        "İZMİR NÖBETÇİ ASLİYE TİCARET MAHKEMESİ'NE\n\nDAVACI : Ege Tekstil A.Ş.\nVEKİLİ : Av. Murat Er\n"
        "DAVALI : Kuzey Konfeksiyon Ltd. Şti.\nKONU : Alacak davasıdır.\n\n"
        "AÇIKLAMALAR :\n"
        "(1) Müvekkil şirket davalıya 2024 yılı boyunca kumaş satmış ve 18 adet fatura düzenlemiştir.\n"
        "(2) Faturaların toplamı 527.300,00 TL olup davalı bu faturalara süresinde itiraz etmemiştir.\n"
        "(3) Davalı 05.03.2025 tarihinde 100.000,00 TL ödemiş, kalan borcunu ödememiştir.\n\n"
        "HUKUKİ SEBEPLER : TTK md. 21, TBK.\n\n"
        "DELİLLER :\n- Faturalar\n- Ticari defter ve kayıtlar\n- Banka kayıtları\n- Bilirkişi incelemesi\n\n"
        "SONUÇ VE İSTEM : Davanın kabulüne karar verilmesini arz ederiz.",
        iddialar=["Müvekkil şirket davalıya 2024", "Faturaların toplamı", "Davalı 05.03.2025"],
        deliller=[("Faturalar", "eksik"), ("Ticari defter ve kayıtlar", "eksik"), ("Banka kayıtları", "dis_kaynak"),
                  ("Bilirkişi incelemesi", "belge_disi")],
        etiketler=[("05.03.2025", "tarih", None), ("100.000,00 TL", "tutar", None)],
    ),
    Dilekce(
        "Yeni saklı 2 - kira tespiti, birleşik başlık",
        "BURSA 4. SULH HUKUK MAHKEMESİ'NE\n\nDAVACI (KİRAYA VEREN) : Nuri Taş\nDAVALI (KİRACI) : Bahar Gök\n\n"
        "OLAY VE AÇIKLAMALAR\n"
        "Davalı, müvekkile ait Nilüfer ilçesindeki daireyi 01.05.2019 başlangıç tarihli sözleşme ile kiralamıştır.\n\n"
        "Aylık kira bedeli bugün 9.500,00 TL olup emsal kira bedellerinin çok altındadır.\n\n"
        "Beş yıllık süre dolduğundan kira bedelinin hakkaniyete uygun olarak yeniden belirlenmesi gerekmektedir.\n\n"
        "DELİLLER\nKira sözleşmesi, emsal kira sözleşmeleri, keşif, bilirkişi incelemesi, tapu kaydı.\n\n"
        "SONUÇ\nKira bedelinin aylık 22.000,00 TL olarak tespitine karar verilmesini talep ederiz.",
        iddialar=["Davalı, müvekkile ait", "Aylık kira bedeli bugün", "Beş yıllık süre dolduğundan"],
        deliller=[("Kira sözleşmesi", "eksik"), ("emsal kira sözleşmeleri", "eksik"), ("keşif", "belge_disi"),
                  ("bilirkişi incelemesi", "belge_disi"), ("tapu kaydı", "dis_kaynak")],
        etiketler=[("01.05.2019", "tarih", "kira başlangıç tarihi"), ("9.500,00 TL", "tutar", None)],
    ),
    Dilekce(
        "Yeni saklı 3 - cevap, büyük harfli maddeler",
        "İSTANBUL ANADOLU 9. ASLİYE HUKUK MAHKEMESİ'NE\n\nESAS NO : 2025/412\nDAVALI : Selim Kurt\n\n"
        "CEVAPLARIMIZ :\n"
        "A) Dava konusu kazada müvekkilin herhangi bir kusuru bulunmamaktadır.\n"
        "B) Kaza 22.08.2024 günü yağmurlu havada meydana gelmiş, davacı araç hızını yola uygun ayarlamamıştır.\n"
        "C) Davacının talep ettiği 63.000,00 TL değer kaybı fahiştir.\n\n"
        "DELİLLER : Kaza tespit tutanağı, olay yeri fotoğrafları, sigorta hasar dosyası, tanık Hakan Öz.\n\n"
        "NETİCE-İ TALEP : Davanın reddine karar verilmesini arz ederiz.",
        iddialar=["Dava konusu kazada", "Kaza 22.08.2024 günü", "Davacının talep ettiği"],
        deliller=[("Kaza tespit tutanağı", "eksik"), ("olay yeri fotoğrafları", "eksik"),
                  ("sigorta hasar dosyası", "dis_kaynak"), ("tanık Hakan Öz", "belge_disi")],
        etiketler=[("22.08.2024", "tarih", "olay tarihi")],
    ),
    Dilekce(
        "Yeni saklı 4 - menfi tespit, vakıalar",
        "KAYSERİ 2. ASLİYE TİCARET MAHKEMESİ'NE\n\nDAVACI : Toros Yem San. A.Ş.\nDAVALI : Karaca Faktoring A.Ş.\n"
        "KONU : Menfi tespit talebimizden ibarettir.\n\n"
        "VAKIALAR\n"
        "1) Müvekkil şirket, 15.07.2024 vadeli 85.000,00 TL bedelli çeki ödeme amacıyla değil teminat olarak vermiştir.\n"
        "2) Teminat konusu iş ilişkisi sona ermiş, çekin iadesi gerekirken davalıya ciro edilmiştir.\n"
        "3) Davalı faktoring şirketi çekin teminat çeki olduğunu bilerek iktisap etmiştir.\n\n"
        "HUKUKİ NEDENLER : TTK md. 818 vd.\n\n"
        "DELİLLER\n1) Çek fotokopisi\n2) Taraflar arasındaki yazışmalar\n3) Davalı şirket kayıtları\n4) Yemin\n\n"
        "TALEP SONUCU : Müvekkilin borçlu olmadığının tespitine karar verilmesini arz ederiz.",
        iddialar=["Müvekkil şirket, 15.07.2024", "Teminat konusu iş", "Davalı faktoring şirketi"],
        deliller=[("Çek fotokopisi", "eksik"), ("Taraflar arasındaki yazışmalar", "eksik"),
                  ("Davalı şirket kayıtları", "dis_kaynak"), ("Yemin", "belge_disi")],
    ),
]
