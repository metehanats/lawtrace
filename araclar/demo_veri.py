"""Yerel geliştirme için sentetik demo verisi.

YALNIZCA YEREL GELİŞTİRME İÇİNDİR. Tüm kişiler, kurumlar, tutarlar ve belgeler
uydurmadır. Aşağıdaki demo parolaları gerçek bir hesapta kullanılmamalıdır.

Oluşturulanlar:
- "Demo Hukuk Bürosu" ve üç kullanıcı (yönetici, avukat, stajyer)
- İki dava dosyası; stajyer yalnızca birincisini görebilir
- Sentetik belgeler: metinli PDF dilekçe, kalitesiz faks taraması (OCR uyarısı
  çıkar), çizgili fatura tablosu taraması, Word bilirkişi raporu
Belgeler yüklendikten sonra metin çıkarma ve OCR görevleri işlenir.

    python araclar/demo_veri.py           # oluştur
    python araclar/demo_veri.py --sifirla # demo bürosunu ve dosyalarını sil, yeniden oluştur
"""

import argparse
import io
import shutil
import sys
from pathlib import Path

import docx
from fpdf import FPDF
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ocr_duzen import tablo  # noqa: E402
from ocr_kalite import BOZULMALAR, YAZI_TIPLERI, sayfa_uret  # noqa: E402

from app import ayarlar  # noqa: E402
from app.belge.api import depolama_al  # noqa: E402
from app.belge.isci import bekleyenleri_isle  # noqa: E402
from app.belge.yukleme import belge_yukle  # noqa: E402
from app.db import engine  # noqa: E402
from app.kimlik import yonetim  # noqa: E402

BURO_ADI = "Demo Hukuk Bürosu"
DEMO_PAROLA = "Demo-Parola-2026"  # yalnızca yerel demo hesapları için
DEMO_ANALIZ_MODELI = "ollama:qwen3.5:4b"
KULLANICILAR = [
    ("Av. Deniz Yönetici", "yonetici@demo.test", "yonetici"),
    ("Av. Ece Avukat", "avukat@demo.test", "avukat"),
    ("Stj. Av. Kerem Stajyer", "stajyer@demo.test", "stajyer"),
]
ARIAL = r"C:\Windows\Fonts\arial.ttf"


def _metinli_pdf(sayfalar: list[list[str]]) -> bytes:
    pdf = FPDF()
    pdf.add_font("arial", fname=ARIAL)
    pdf.set_font("arial", size=12)
    for satirlar in sayfalar:
        pdf.add_page()
        for satir in satirlar:
            pdf.multi_cell(0, 8, satir)
            pdf.ln(2)
    return bytes(pdf.output())


def _taranmis_pdf(goruntuler) -> bytes:
    pdf = FPDF()
    for goruntu in goruntuler:
        pdf.add_page()
        pdf.image(goruntu, x=0, y=0, w=210, h=297)
    return bytes(pdf.output())


def _docx(paragraflar: list[str]) -> bytes:
    belge = docx.Document()
    belge.add_heading("BİLİRKİŞİ RAPORU", level=1)
    for i, p in enumerate(paragraflar):
        if p == "---":
            belge.add_page_break()
        else:
            belge.add_paragraph(p)
    tampon = io.BytesIO()
    belge.save(tampon)
    return tampon.getvalue()


def _belgeler():
    dilekce = _metinli_pdf([
        [
            "T.C. İSTANBUL 7. ASLİYE TİCARET MAHKEMESİ'NE",
            "Esas No: 2025/1487",
            "DAVACI: Ayşe Yılmaz",
            "VEKİLİ: Av. Ece Avukat",
            "DAVALI: Çağlar Gıda Sanayi ve Ticaret A.Ş.",
            "KONU: 386.420,50 TL alacağın faiziyle birlikte tahsili talebidir.",
            "AÇIKLAMALAR: Müvekkil, davalı şirketle 03.11.2024 tarihinde mal satış sözleşmesi "
            "imzalamış ve sözleşme konusu malları eksiksiz teslim etmiştir.",
            "Davalıya 17.02.2025 tarihinde ihtarname gönderilmiş, ancak ödeme yapılmamıştır.",
        ],
        [
            "Davalı şirket, 12 Mart 2025 tarihli yazısıyla borcun bir kısmını kabul etmiştir.",
            "Protokolün 4.2. maddesi uyarınca cezai şart 50.000 TL olarak belirlenmiştir.",
            "DELİLLER: Mal satış sözleşmesi, ihtarname, EK-3 fatura listesi, bilirkişi raporu, "
            "teslim tutanağı, tanık Hüseyin Aksoy beyanı.",
            "SONUÇ VE İSTEM: 386.420,50 TL alacağın yıllık %24,5 faiziyle tahsiline karar verilmesini "
            "saygıyla arz ve talep ederiz.",
        ],
    ])
    faks = _taranmis_pdf([BOZULMALAR["faks"](sayfa_uret(YAZI_TIPLERI["courier"]))])
    golgeli = _taranmis_pdf([BOZULMALAR["golge"](sayfa_uret(YAZI_TIPLERI["times"]))])
    fatura_tablosu = _taranmis_pdf([BOZULMALAR["egik_1.5"](tablo(True).goruntu)])
    bilirkisi = _docx([
        "Dosya: İstanbul 7. Asliye Ticaret Mahkemesi 2025/1487 Esas",
        "İncelenen faturaların toplam tutarı 386.420,50 TL olup, davalı tarafından yapılan "
        "ödeme bulunmamaktadır.",
        "---",
        "Sonuç: Davacının talep edebileceği alacak tutarı 386.420,50 TL'dir.",
    ])
    sozlesme = _metinli_pdf([[
        "MAL SATIŞ SÖZLEŞMESİ",
        "Taraflar: Ayşe Yılmaz (Satıcı) ile Çağlar Gıda Sanayi ve Ticaret A.Ş. (Alıcı)",
        "Sözleşme tarihi: 03.11.2024",
        "Madde 4.2: Ödemenin geciktirilmesi halinde alıcı 50.000 TL cezai şart öder.",
    ]])
    # Özel nitelikli veri içeren örnek: analizden önce avukat onayı ister
    saglik = _metinli_pdf([[
        "EPİKRİZ (SENTETİK ÖRNEK)",
        "Hasta: Ayşe Yılmaz",
        "Yatış tarihi: 20.01.2025 · Taburcu: 24.01.2025",
        "Tanı: Lomber disk hernisi. Ameliyat önerilmemiş, fizik tedavi planlanmıştır.",
        "İş göremezlik süresi 21 gün olarak belirlenmiştir. Tedavi gideri 14.750,00 TL'dir.",
    ]])
    return {
        1: [
            ("Dava dilekçesi.pdf", dilekce),
            ("İhtarname - faks.pdf", faks),
            ("EK-3 Fatura listesi (tarama).pdf", fatura_tablosu),
            ("Bilirkişi raporu.docx", bilirkisi),
            ("Hastane epikrizi.pdf", saglik),
        ],
        2: [
            ("Mal satış sözleşmesi.pdf", sozlesme),
            ("Teslim tutanağı (telefon fotoğrafı).pdf", golgeli),
        ],
    }


def sifirla() -> None:
    with engine().begin() as c:
        burolar = c.execute(text("SELECT id FROM buro WHERE ad = :a"), {"a": BURO_ADI}).scalars().all()
        for buro in burolar:
            # belge -> dava RESTRICT olduğu için önce belgeler; sayfa/görev/oturum/erişim CASCADE ile gider
            for tablo_adi in ("denetim_kaydi", "belge", "dava_dosyasi", "muvekkil", "kullanici"):
                c.execute(text(f"DELETE FROM {tablo_adi} WHERE buro_id = :b"), {"b": buro})
            c.execute(text("DELETE FROM buro WHERE id = :b"), {"b": buro})
            shutil.rmtree(ayarlar.depolama_koku() / str(buro), ignore_errors=True)
    print(f"Silinen demo bürosu: {len(burolar)}")


def olustur() -> None:
    with engine().begin() as c:
        if c.execute(text("SELECT 1 FROM buro WHERE ad = :a"), {"a": BURO_ADI}).first():
            print("Demo bürosu zaten var. Yeniden oluşturmak için --sifirla kullanın.")
            return
        buro = yonetim.buro_ekle(c, BURO_ADI)
        # Demo bürosunda analiz yerel modelle açık (yalnızca sentetik veri)
        yonetim.analiz_ayarla(c, buro, DEMO_ANALIZ_MODELI)
        kimlikler = {
            rol: yonetim.kullanici_ekle(c, buro_id=buro, ad_soyad=ad, e_posta=e_posta, rol=rol, parola=DEMO_PAROLA)
            for ad, e_posta, rol in KULLANICILAR
        }
        muvekkil1 = c.execute(text("INSERT INTO muvekkil (buro_id, tur, ad_unvan) "
                                   "VALUES (:b, 'gercek_kisi', 'Ayşe Yılmaz') RETURNING id"), {"b": buro}).scalar_one()
        muvekkil2 = c.execute(text("INSERT INTO muvekkil (buro_id, tur, ad_unvan) "
                                   "VALUES (:b, 'tuzel_kisi', 'Kuzey Lojistik Ltd. Şti.') RETURNING id"),
                              {"b": buro}).scalar_one()
        davalar = {}
        for no, (dosya_no, baslik, tur, muvekkil) in enumerate([
            ("2025/1487", "Ayşe Yılmaz - Çağlar Gıda alacak davası", "Alacak", muvekkil1),
            ("2026/0312", "Kuzey Lojistik - ayıplı mal itirazı", "Ticari", muvekkil2),
        ], start=1):
            davalar[no] = c.execute(
                text("INSERT INTO dava_dosyasi (buro_id, muvekkil_id, dosya_no, baslik, dava_turu, "
                     "olusturan_kullanici_id) VALUES (:b, :m, :n, :t, :tur, :k) RETURNING id"),
                {"b": buro, "m": muvekkil, "n": dosya_no, "t": baslik, "tur": tur, "k": kimlikler["yonetici"]},
            ).scalar_one()
        erisimler = [(1, "avukat", "sorumlu"), (2, "avukat", "sorumlu"), (1, "stajyer", "inceleyen")]
        for dava_no, rol, erisim_rolu in erisimler:
            c.execute(text("INSERT INTO dosya_erisim (dava_dosyasi_id, kullanici_id, rol) VALUES (:d, :k, :r)"),
                      {"d": davalar[dava_no], "k": kimlikler[rol], "r": erisim_rolu})

        depolama = depolama_al()
        sayi = 0
        for dava_no, belgeler in _belgeler().items():
            for ad, veri in belgeler:
                belge_yukle(c, depolama, dava_id=davalar[dava_no], kullanici_id=kimlikler["avukat"],
                            orijinal_ad=ad, veri=veri)
                sayi += 1
    print(f"Demo bürosu oluşturuldu: {len(KULLANICILAR)} kullanıcı, 2 dava, {sayi} belge.")
    print("Belgeler işleniyor (metin çıkarma ve OCR)...")
    islenen = bekleyenleri_isle(engine().begin, depolama_al())
    print(f"{islenen} görev işlendi.")
    print("Demo hesapları ve parolası bu dosyanın başında (KULLANICILAR, DEMO_PAROLA).")


def main() -> None:
    ayristirici = argparse.ArgumentParser(description="Sentetik demo verisi")
    ayristirici.add_argument("--sifirla", action="store_true", help="Demo bürosunu silip yeniden oluştur")
    if ayristirici.parse_args().sifirla:
        sifirla()
    olustur()


if __name__ == "__main__":
    main()
