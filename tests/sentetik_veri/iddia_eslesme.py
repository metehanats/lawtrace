"""İddia–belge eşleme seti: bir iddia dosyadaki hangi belgelerle ilgilidir?
TÜM İÇERİK UYDURMADIR (kişi, kurum, tutar, tarih, plaka, dosya no).

Mevcut kurallar (app/analiz/iddia.py) bağı ancak belgenin adı iddiada geçiyorsa, Ek-N atfı ya da
aynı tarih/tutar varsa kurar. Bu set, iddianın belgeyi ADIYLA ANMADAN anlattığı durumları da içerir
("resmi yoldan uyarılmış" → ihtarname; "uzman incelemesiyle belirlenmiş" → ekspertiz raporu).

Her iddia için:
- beklenen: iddiayı doğrudan destekleyen ya da çürüten belgeler (bağ kurulmalı),
- kabul: ilgili sayılabilecek ama zorunlu olmayan belgeler (bağ kurulursa yanlış sayılmaz),
- beklenen boşsa iddia hiçbir belgeyle ilgili değildir; kurulan her bağ yanlıştır.

İki bölüm (bkz. dilekce_cesitlilik.py):
- GELISTIRME: yöntem (istem, kural) ayarlanırken bakılır.
- SAKLI: yöntem yazılmadan ÖNCE yazıldı; ayarlama sırasında bakılmaz.

Sınır: iki bölümü de aynı kişi (Claude) yazdı; belgeler kısa ve temizdir (gerçek belgeler uzun,
OCR'lı ve gürültülüdür). Sonuçlar yöntemleri karşılaştırmak içindir, gerçek başarıyı göstermez.
"""

from dataclasses import dataclass, field


@dataclass
class Belge:
    ad: str
    metin: str


@dataclass
class Iddia:
    metin: str
    beklenen: set[str]
    kabul: set[str] = field(default_factory=set)


@dataclass
class Dosya:
    ad: str
    belgeler: list[Belge]
    iddialar: list[Iddia]


GELISTIRME = [
    Dosya(
        "Gelişim 1 - mal satışından alacak",
        [
            Belge("Satış sözleşmesi.pdf",
                  "MAL SATIŞ SÖZLEŞMESİ\nTaraflar Orman Kereste Ltd. Şti. (satıcı) ile Kaya Yapı A.Ş. (alıcı) "
                  "arasında 14.02.2024 tarihinde imzalanmıştır. Satıcı 120 m3 çam kereste teslim edecek, alıcı "
                  "bedeli teslimden itibaren 30 gün içinde ödeyecektir. Toplam bedel 245.000,00 TL'dir."),
            Belge("Sevk irsaliyeleri.pdf",
                  "SEVK İRSALİYESİ\nİrsaliye No: 0045. Sevk tarihi 02.03.2024. 120 m3 çam kereste Kaya Yapı A.Ş. "
                  "şantiyesine teslim edilmiş, teslim alan Mehmet Kara imzalamıştır."),
            Belge("Noter ihtarı.pdf",
                  "İHTARNAME\nBeyoğlu 12. Noterliği, 01.04.2024 tarih ve 08812 yevmiye. Muhatap Kaya Yapı A.Ş.'ye, "
                  "245.000,00 TL tutarındaki borcun 7 gün içinde ödenmesi, aksi halde yasal yollara "
                  "başvurulacağı ihtar olunur."),
            Belge("Banka hesap ekstresi.pdf",
                  "HESAP EKSTRESİ\n01.03.2024 - 30.04.2024 dönemi. 15.03.2024 tarihinde Kaya Yapı A.Ş.'den "
                  "50.000,00 TL gelen havale. Başka tahsilat bulunmamaktadır."),
            Belge("Fotoğraflar.pdf", "FOTOĞRAF EKİ\nŞantiye girişinde istiflenmiş kereste yığınının görünümü."),
        ],
        [
            Iddia("Müvekkil şirket ile davalı arasında 14.02.2024 tarihinde kereste tedarikine ilişkin anlaşma "
                  "yapılmıştır.", {"Satış sözleşmesi.pdf"}),
            Iddia("Müvekkil, edimini yerine getirerek malların tamamını davalının şantiyesine ulaştırmıştır.",
                  {"Sevk irsaliyeleri.pdf"}, {"Fotoğraflar.pdf"}),
            Iddia("Davalı, borcunu ödemesi için resmi yoldan uyarılmış ancak buna rağmen ödeme yapmamıştır.",
                  {"Noter ihtarı.pdf"}, {"Banka hesap ekstresi.pdf"}),
            Iddia("Davalı yalnızca 50.000,00 TL kısmi ödeme yapmış, bakiye borç ödenmemiştir.",
                  {"Banka hesap ekstresi.pdf"}),
            Iddia("Davalı şirketin ticari itibarı sektörde zayıflamış olup başka alacaklıları da bulunmaktadır.",
                  set()),
            Iddia("Taraflar arasındaki ödeme vadesi teslimden itibaren otuz gündür.", {"Satış sözleşmesi.pdf"}),
        ],
    ),
    Dosya(
        "Gelişim 2 - işçilik alacakları",
        [
            Belge("SGK hizmet dökümü.pdf",
                  "SGK HİZMET DÖKÜMÜ\nSelin Aydın, Deniz Otelcilik A.Ş. işyerinde 01.06.2018 giriş, 30.09.2024 "
                  "çıkış. Çıkış kodu 04: işveren tarafından haklı neden bildirilmeden fesih."),
            Belge("Ücret bordroları.pdf",
                  "ÜCRET BORDROSU\nEylül 2024 dönemi. Net ücret 31.000,00 TL. Fazla mesai satırı boş, fazla mesai "
                  "ödemesi yapılmamıştır."),
            Belge("Fesih bildirimi.pdf",
                  "FESİH BİLDİRİMİ\nSayın Selin Aydın, iş sözleşmeniz 30.09.2024 tarihi itibarıyla sona "
                  "erdirilmiştir. Bildirimde fesih gerekçesi belirtilmemiştir."),
            Belge("Puantaj kayıtları.pdf",
                  "PUANTAJ\nTemmuz-Eylül 2024. Haftalık çalışma süresi ortalama 60 saat olarak kaydedilmiştir."),
            Belge("Arabuluculuk son tutanağı.pdf",
                  "ARABULUCULUK SON TUTANAĞI\n12.11.2024 tarihli görüşmede taraflar anlaşamamıştır."),
        ],
        [
            Iddia("Müvekkil davalıya ait otelde 01.06.2018 tarihinden itibaren kesintisiz çalışmıştır.",
                  {"SGK hizmet dökümü.pdf"}),
            Iddia("Müvekkilin aldığı son aylık net ücret 31.000,00 TL'dir.", {"Ücret bordroları.pdf"}),
            Iddia("İşveren, iş ilişkisini hiçbir gerekçe göstermeden sona erdirmiştir.",
                  {"Fesih bildirimi.pdf", "SGK hizmet dökümü.pdf"}),
            Iddia("Müvekkil yasal sınırın üzerinde çalıştırılmış, bunun karşılığı kendisine verilmemiştir.",
                  {"Puantaj kayıtları.pdf", "Ücret bordroları.pdf"}),
            Iddia("Dava şartı olan zorunlu uyuşmazlık çözüm yoluna başvurulmuş, sonuç alınamamıştır.",
                  {"Arabuluculuk son tutanağı.pdf"}),
            Iddia("Müvekkil işyerinde mobbinge maruz kalmış, sağlığı bozulmuştur.", set()),
        ],
    ),
    Dosya(
        "Gelişim 3 - trafik kazası",
        [
            Belge("Kaza tespit tutanağı.pdf",
                  "TRAFİK KAZASI TESPİT TUTANAĞI\n14.06.2024 saat 18.40, Atatürk Bulvarı kavşağı. A aracı "
                  "(34 ABC 123) kırmızı ışıkta durmakta iken B aracı (06 XYZ 987) arkadan çarpmıştır. Kusur: B "
                  "aracı sürücüsü asli kusurlu."),
            Belge("Ekspertiz raporu.pdf",
                  "EKSPERTİZ RAPORU\n34 ABC 123 plakalı araçta arka tampon, bagaj kapağı ve stop lambası hasarı "
                  "tespit edilmiştir. Onarım bedeli 84.300 TL olarak hesaplanmıştır."),
            Belge("Sigorta ödeme yazısı.pdf",
                  "Güven Sigorta A.Ş. HASAR ÖDEME BİLDİRİMİ\nDosya 2024/7781 kapsamında 27.06.2024 tarihinde "
                  "41.000 TL ödeme yapılmıştır."),
            Belge("Araç ruhsatı.pdf", "ARAÇ TESCİL BELGESİ\n34 ABC 123, 2019 model, sahibi Ahmet Demir."),
            Belge("Tanık listesi.docx", "TANIK LİSTESİ\n1- Elif Şahin, Kadıköy/İstanbul."),
        ],
        [
            Iddia("Kaza anında müvekkilin aracı ışıkta beklemekteydi ve çarpma arkadan gerçekleşti.",
                  {"Kaza tespit tutanağı.pdf"}),
            Iddia("Aracın onarımı için gereken masraf uzman incelemesiyle belirlenmiştir.", {"Ekspertiz raporu.pdf"}),
            Iddia("Karşı tarafın sigortacısı zararın bir kısmını karşılamıştır.", {"Sigorta ödeme yazısı.pdf"}),
            Iddia("Hasarlı araç müvekkile aittir.", {"Araç ruhsatı.pdf"}),
            Iddia("Olayı gören bağımsız bir kişi, kazanın nasıl olduğunu anlatacaktır.", {"Tanık listesi.docx"}),
            Iddia("Müvekkil kazadan sonra iki hafta işe gidememiş ve gelir kaybına uğramıştır.", set()),
        ],
    ),
    Dosya(
        "Gelişim 4 - kira",
        [
            Belge("Kira sözleşmesi.pdf",
                  "KİRA SÖZLEŞMESİ\nKiraya veren Hasan Yılmaz, kiracı Zeynep Koç. Başlangıç 01.09.2022, aylık kira "
                  "18.000 TL, her ayın 5'inde banka hesabına ödenir."),
            Belge("Dekontlar.pdf",
                  "BANKA DEKONTU\n05.01.2025 tarihinde Zeynep Koç'tan Hasan Yılmaz'a 18.000 TL kira bedeli EFT. "
                  "05.02.2025 tarihinde 18.000 TL kira bedeli EFT."),
            Belge("Tahliye taahhütnamesi.pdf",
                  "TAHLİYE TAAHHÜTNAMESİ\nKiracı, taşınmazı 31.08.2025 tarihinde boşaltacağını taahhüt eder."),
            Belge("WhatsApp yazışmaları.pdf",
                  "Ekran görüntüsü. Kiraya veren: 'Mart kirası gelmedi.' Kiracı: 'Mart kirasını elden verdim, "
                  "makbuz istemediniz.'"),
        ],
        [
            Iddia("Kiracı, ocak ve şubat aylarına ait kira bedellerini zamanında ödemiştir.", {"Dekontlar.pdf"},
                  {"Kira sözleşmesi.pdf"}),
            Iddia("Kira ilişkisi 2022 yılı eylül ayında başlamıştır.", {"Kira sözleşmesi.pdf"}),
            Iddia("Mart ayı kirasının elden ödendiği kiracı tarafından bildirilmiştir.", {"WhatsApp yazışmaları.pdf"}),
            Iddia("Kiracı taşınmazı belirli bir tarihte boşaltmayı yazılı olarak üstlenmiştir.",
                  {"Tahliye taahhütnamesi.pdf"}),
            Iddia("Taşınmazda kiracıdan kaynaklanan su kaçağı hasarı oluşmuştur.", set()),
        ],
    ),
]


SAKLI = [
    Dosya(
        "Saklı 1 - iş kazası",
        [
            Belge("İş kazası bildirimi.pdf",
                  "SGK İŞ KAZASI BİLDİRGESİ\nKazalı: Murat Çelik. Kaza tarihi 08.03.2025. İskele kurulurken 4 metre "
                  "yükseklikten düşme."),
            Belge("Hastane epikrizi.pdf",
                  "EPİKRİZ\nHasta Murat Çelik, 08.03.2025 acil başvuru. Sol bilek kırığı, 45 gün istirahat raporu "
                  "verilmiştir."),
            Belge("İSG eğitim kayıtları.pdf",
                  "İŞ SAĞLIĞI VE GÜVENLİĞİ EĞİTİM KATILIM FORMU\nMurat Çelik, yüksekte çalışma eğitimi almamıştır; "
                  "listede imzası bulunmamaktadır."),
            Belge("Maaş bordrosu.pdf", "ÜCRET BORDROSU\nŞubat 2025, Murat Çelik, net ücret 26.400 TL."),
        ],
        [
            Iddia("Müvekkil çalıştığı inşaatta yüksekten düşerek yaralanmıştır.", {"İş kazası bildirimi.pdf"},
                  {"Hastane epikrizi.pdf"}),
            Iddia("Müvekkilin elinde kemik kırılmış ve uzun süre çalışamamıştır.", {"Hastane epikrizi.pdf"}),
            Iddia("İşveren, müvekkile yüksekte güvenli çalışma konusunda gerekli eğitimi vermemiştir.",
                  {"İSG eğitim kayıtları.pdf"}),
            Iddia("Kazadan önceki son aylık kazancı 26.400 TL'dir.", {"Maaş bordrosu.pdf"}),
            Iddia("İşveren kazadan sonra müvekkili işten çıkarmakla tehdit etmiştir.", set()),
        ],
    ),
    Dosya(
        "Saklı 2 - ayıplı ürün",
        [
            Belge("Fatura.pdf",
                  "E-ARŞİV FATURA\nAlıcı: Gül Arslan. Ürün: Bulaşık makinesi BM-600. Tarih 10.01.2025. Tutar "
                  "21.750,00 TL."),
            Belge("Servis raporu.pdf",
                  "TEKNİK SERVİS RAPORU\nBM-600 cihazında pompa arızası, 3. kez aynı arıza. Onarım ile "
                  "giderilemeyecek üretim hatası."),
            Belge("Satıcıya başvuru e-postası.pdf",
                  "E-posta, 20.02.2025: 'Makine üçüncü kez arızalandı, ürünün yenisiyle değiştirilmesini talep "
                  "ediyorum.' Satıcı yanıt vermemiştir."),
            Belge("Garanti belgesi.pdf", "GARANTİ BELGESİ\nBM-600, garanti süresi 2 yıl, satış tarihi 10.01.2025."),
        ],
        [
            Iddia("Tüketici ürünü ocak ayında 21.750,00 TL bedelle satın almıştır.", {"Fatura.pdf"},
                  {"Garanti belgesi.pdf"}),
            Iddia("Ürün tekrar eden ve onarılamayan bir imalat kusuru taşımaktadır.", {"Servis raporu.pdf"}),
            Iddia("Tüketici seçimlik hakkını kullanarak değişim istemiş, satıcı sessiz kalmıştır.",
                  {"Satıcıya başvuru e-postası.pdf"}),
            Iddia("Arıza, ürünün güvence süresi içinde ortaya çıkmıştır.", {"Garanti belgesi.pdf"},
                  {"Servis raporu.pdf", "Fatura.pdf"}),
            Iddia("Satıcı mağazada tüketiciye kaba davranmıştır.", set()),
        ],
    ),
    Dosya(
        "Saklı 3 - itirazın iptali",
        [
            Belge("Cari hesap ekstresi.pdf",
                  "CARİ HESAP EKSTRESİ\nBorçlu Ege Gıda Ltd. 31.12.2024 itibarıyla bakiye borç 132.480,00 TL."),
            Belge("İcra takip talebi.pdf",
                  "TAKİP TALEBİ\nİzmir 5. İcra Dairesi 2025/1120 E. Alacak 132.480,00 TL, takip tarihi 15.01.2025."),
            Belge("Borca itiraz dilekçesi.pdf",
                  "İTİRAZ DİLEKÇESİ\nBorçlu Ege Gıda Ltd. borcun tamamına ve ferilerine itiraz etmiştir. Tarih "
                  "22.01.2025."),
            Belge("Teslim tutanakları.pdf",
                  "MAL TESLİM TUTANAĞI\nZeytinyağı 400 teneke, teslim alan Ege Gıda depo sorumlusu, 05.11.2024."),
        ],
        [
            Iddia("Borçlu, ticari ilişki kapsamında kendisine gönderilen ürünleri teslim almıştır.",
                  {"Teslim tutanakları.pdf"}),
            Iddia("Müvekkilin defter kayıtlarına göre borçlunun ödenmemiş bakiyesi bulunmaktadır.",
                  {"Cari hesap ekstresi.pdf"}),
            Iddia("Alacağın tahsili için başlatılan yasal süreç borçlunun karşı çıkması üzerine durmuştur.",
                  {"Borca itiraz dilekçesi.pdf", "İcra takip talebi.pdf"}),
            Iddia("Borçlu, alacaklıya hiçbir zaman şikâyette bulunmamıştır.", set()),
        ],
    ),
    Dosya(
        "Saklı 4 - kat mülkiyeti",
        [
            Belge("Bilirkişi raporu.pdf",
                  "BİLİRKİŞİ RAPORU\nÜst kattaki daireden kaynaklanan su sızıntısı nedeniyle alt kat tavanında "
                  "6 m2 küf ve boya dökülmesi tespit edilmiştir. Zarar 14.200 TL."),
            Belge("Yönetim kurulu kararı.pdf",
                  "APARTMAN YÖNETİM KURULU KARARI\n03.04.2025 toplantısında 5 no.lu daire maliki Kemal Uçar'a "
                  "tesisatı onarması için 15 gün süre verilmiştir."),
            Belge("Fotoğraf eki.pdf", "FOTOĞRAFLAR\nAlt kat banyo tavanındaki ıslaklık ve küf lekelerinin görünümü."),
        ],
        [
            Iddia("Üst kattaki tesisat arızası alt kattaki daireye zarar vermiştir.", {"Bilirkişi raporu.pdf"},
                  {"Fotoğraf eki.pdf"}),
            Iddia("Davalıya onarım için süre tanınmış, ancak davalı gereğini yapmamıştır.",
                  {"Yönetim kurulu kararı.pdf"}),
            Iddia("Tavandaki hasar gözle görülür durumdadır.", {"Fotoğraf eki.pdf"}, {"Bilirkişi raporu.pdf"}),
            Iddia("Davalı daha önce de başka komşularla benzer sorunlar yaşamıştır.", set()),
        ],
    ),
]
