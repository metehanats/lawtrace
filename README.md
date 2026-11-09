# LawTrace (Hukuk Dava Analizi MVP)

> Her bulgunun izi belgesinde.

Not: Proje klasörü (`AvukatDosyaTakip`), veri klasörü (`AvukatDosyaTakipVeri`) ve zamanlanmış
görev adı (`AvukatDosyaTakip Yedek`) kurulu düzeni bozmamak için eski adlarıyla kalır.

Türkiye'deki küçük hukuk büroları için, dava dosyalarındaki belgeleri inceleyen,
bulguları kaynak sayfa ve alıntılarıyla gösteren ve avukatın onayına açan bir çalışma ortamı.

## Temel ilkeler

- Her yapay zekâ bulgusu bir kaynak alıntıya (belge + sayfa + metin) bağlıdır. Kaynaksız bulgu kaydedilmez.
- Bulgular varsayılan olarak "otomatik" işaretlenir; avukat onayı olmadan kesin gerçek gibi sunulmaz.
- Müvekkil verisi şifreli saklanır, her erişim denetim kaydına yazılır.
- Gerçek müvekkil verisi geliştirme ve test ortamında kullanılmaz; yalnızca sentetik veri.

## Klasör yapısı

| Klasör | İçerik |
|---|---|
| `db/` | PostgreSQL şeması ve migrasyonlar |
| `app/` | FastAPI uygulaması (modüler monolit) |
| `tests/sentetik_veri/` | Gerçek olmayan örnek dava dosyaları ve beklenen sonuçlar |
| `araclar/` | Demo verisi, ölçüm betikleri, arayüz testi sunucusu |
| `calistir/` | Windows için başlatma ve yedek görevi betikleri |
| `frontend/` | Next.js arayüzü ve Playwright arayüz testleri |

## Teknoloji yığını (önerilen)

- Backend: Python, FastAPI
- Veritabanı: PostgreSQL 15+
- Dosya depolama: Şifreli, S3 uyumlu nesne depolama (Türkiye veya AB bölgesi)
- İş kuyruğu: Redis tabanlı (Celery veya RQ)
- Arayüz: React (Next.js), mobil uyumlu web

## Durum

- [x] Klasör iskeleti
- [x] İlk veri modeli ve SQL şeması (`db/schema.sql`)
- [x] Migrasyon aracı: Alembic (yerel PostgreSQL 18 üzerinde uygulandı)
- [x] Belge yükleme, metin çıkarma, OCR (Tesseract, Türkçe) ve işçi süreci
- [x] Belge listeleme/görüntüleme, denetim kaydı (erişim reddi dahil)
- [x] Kimlik doğrulama (parola + oturum çerezi, hesap kilidi)
- [x] Arayüz (Next.js): giriş, dava dosyaları, belge yükleme ve görüntüleme
- [x] Müvekkil ve dava oluşturma, dosya erişimi yönetimi, müvekkil bilgisinin şifrelenmesi
- [x] Kaynaklı analiz (ilk sürüm): tarih, tutar, kişi, kurum; yerel model (Ollama); özel nitelikli veri onay kapısı; avukat onayı/reddi
- [x] Belgeler arası çelişki, zaman çizelgesi, iddia–delil haritası
- [x] Bulgu düzeltme ve avukatın etiket seçmesi; müvekkil, dava ve kullanıcı düzenleme; kapalı dosya salt okunur
- [x] Yönetim ekranları, denetim kaydı ekranı, şifreli ve doğrulanan otomatik yedek
- [x] Arayüz testleri (Playwright, Microsoft Edge)

## Çalıştırma

Gizli değerler dosyalarda değil, kullanıcı ortam değişkenlerinde tutulur: `DATABASE_URL`, `MUVEKKIL_ANAHTARI`
(şifreleme anahtarı) ve testler için `AVUKAT_PG_SUPERPW`. Sonra (PowerShell, proje kökünde):

```powershell
.\db\db-baslat.ps1        # veritabanı
.\calistir\api.ps1        # API (ayrı terminal)
.\calistir\isci.ps1       # belge işleme işçisi (ayrı terminal)
.\calistir\arayuz.ps1     # arayüz: http://localhost:3000 (ayrı terminal)
```
