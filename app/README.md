# app/

FastAPI tabanlı modüler monolit. Modüller:

- `kimlik/`: giriş, oturum, parola; büro ve kullanıcı yönetim komutları (`python -m app.kimlik.yonetim`)
- `dava/`: dava dosyası listesi ve ayrıntısı
- `belge/`: yükleme, erişim denetimi, metin çıkarma, OCR, ön işleme, işçi, görüntüleme
- `denetim.py`: denetim kaydı; `web.py`: HTTP yardımcıları; `ayarlar.py`: ortam değişkenleri

Henüz yazılmayanlar: `analiz/` (kaynaklı yapay zekâ analizi), `kronoloji/` (olay zaman çizelgesi),
`delil/` (iddia ve delil haritası).
