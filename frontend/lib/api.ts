// FastAPI ile konuşan ince katman. Tüm istekler aynı kaynaktaki /api üzerinden gider
// (next.config.ts içindeki yönlendirme); oturum HttpOnly çerezde, JavaScript onu görmez.

export class OturumYok extends Error {}

export class ApiHatasi extends Error {
  constructor(public durum: number, mesaj: string) {
    super(mesaj);
  }
}

export async function api<T>(yol: string, secenek: RequestInit = {}): Promise<T> {
  const yanit = await fetch(`/api${yol}`, { credentials: "same-origin", cache: "no-store", ...secenek });
  if (yanit.status === 401 && !yol.startsWith("/oturum/giris")) throw new OturumYok();
  if (!yanit.ok) {
    let mesaj = `Beklenmeyen hata (${yanit.status}).`;
    try {
      const govde = await yanit.json();
      if (typeof govde.detail === "string") mesaj = govde.detail;
      else if (yanit.status === 422) mesaj = "Gönderilen bilgiler geçersiz.";
    } catch {
      // gövde JSON değil
    }
    throw new ApiHatasi(yanit.status, mesaj);
  }
  if (yanit.status === 204) return undefined as T;
  return (await yanit.json()) as T;
}

export function jsonGonder<T>(yol: string, govde: unknown): Promise<T> {
  return api<T>(yol, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(govde),
  });
}

// --- Türler (FastAPI yanıtlarıyla aynı alan adları) ---

export type Kullanici = {
  id: string;
  ad_soyad: string;
  e_posta: string;
  rol: "yonetici" | "avukat" | "stajyer";
  buro_id: string;
  buro_adi: string;
  parola_degismeli: boolean;      // geçici parolayla girildi; değiştirene kadar başka işlem yapılamaz
};

export type YonetimKullanicisi = {
  id: string;
  ad_soyad: string;
  e_posta: string;
  rol: Kullanici["rol"];
  aktif: boolean;
  parolasi_var: boolean;
  parola_degismeli: boolean;
  kilitli: boolean;
  kilit_bitis: string | null;
  son_giris: string | null;
  olusturma: string;
};

export type DenetimKaydi = {
  id: number;
  zaman: string;
  eylem: string;
  hedef_tur: string;
  hedef_id: string | null;
  ip_adresi: string | null;
  ayrinti: Record<string, unknown> | null;
  kullanici_id: string | null;
  kullanici_adi: string | null;
  kullanici_e_posta: string | null;
  hedef_adi: string | null;        // yalnızca hedef aynı bürodaysa dolu
  hedef_dava_id: string | null;
  hedef_belge_id: string | null;
};

export type DenetimOzeti = {
  eylemler: Record<string, number>;
  reddedilen_kullanicilar: { kullanici_id: string | null; ad_soyad: string | null; sayi: number; son_zaman: string }[];
  kilitlenen_hesaplar: { kullanici_id: string; ad_soyad: string; zaman: string }[];
};

export const EYLEM: Record<string, string> = {
  goruntuleme: "Görüntüleme", yukleme: "Yükleme", silme: "Silme", onay: "Onay", reddetme: "Ret",
  disa_aktarim: "Dışa aktarım", erisim_reddi: "Erişim reddi", giris: "Giriş", giris_basarisiz: "Başarısız giriş",
  cikis: "Çıkış", olusturma: "Oluşturma", erisim_degisikligi: "Yetki değişikliği", analiz: "Analiz",
  guncelleme: "Güncelleme",
};

export const HEDEF_TURU: Record<string, string> = {
  dava_dosyasi: "Dava dosyası", dava_listesi: "Dava listesi", belge: "Belge", belge_sayfa: "Belge sayfası",
  belge_listesi: "Belge listesi", bulgu: "Bulgu", bulgu_listesi: "Bulgular", zaman_cizelgesi: "Zaman çizelgesi",
  iddia_haritasi: "İddia–delil haritası", uyusmazlik: "Çelişki", kullanici: "Kullanıcı",
  kullanici_listesi: "Kullanıcı listesi", muvekkil: "Müvekkil", muvekkil_listesi: "Müvekkil listesi",
  oturum: "Oturum", buro: "Büro", denetim_kaydi: "Denetim kaydı",
};

export type YedekDurumu = {
  son_basarili: { zaman: string; klasor: string; belge_sayisi: number; dogrulanan_belge: number; silinen: string[] } | null;
  son_deneme: { zaman: string; durum: "basarili" | "hata"; mesaj?: string } | null;
  yedek_sayisi: number;
  uyari: boolean;   // son başarılı yedek 36 saatten eski ya da son deneme hatalı
};

export type BuroAyarlari = {
  id: string;
  ad: string;
  analiz_modeli: string | null;
  yerel_modeller: string[] | null;   // null: yerel model sunucusuna ulaşılamadı
};

export type Dava = {
  id: string;
  dosya_no: string;
  baslik: string;
  dava_turu: string | null;
  durum: "acik" | "kapali" | "beklemede";
  muvekkil_id: string;
  muvekkil: string;
  belge_sayisi: number;
  islenen_belge_sayisi: number;
  guncelleme: string;
  // Dosyada avukatı bekleyen işler (Özet sekmesiyle aynı tanımlar)
  incelenmemis_bulgu: number;
  acik_celiski: number;
  kontrol_ocr_sayfa: number;
  onay_bekleyen_belge: number;
  // Yalnızca ayrıntı ucunda: dosyanın sorumlusu ya da yönetici (stajyer değil)
  duzenleyebilir?: boolean;
};

export type BelgeDurumu = "yuklendi" | "isleniyor" | "hazir" | "hata";

export type BelgeOzeti = {
  id: string;
  orijinal_ad: string;
  mime_tur: string;
  durum: BelgeDurumu;
  sayfa_sayisi: number | null;
  yuklenme: string;
  ocr_sayfa_sayisi: number;
  uyarili_sayfa_sayisi: number;
};

export type BelgeListesi = { toplam: number; limit: number; offset: number; belgeler: BelgeOzeti[] };

export type SayfaOzeti = {
  sayfa_no: number;
  metin_kaynagi: "dogrudan" | "ocr";
  ocr_guven_skoru: number | null;
  karakter_sayisi: number;
  asliyla_karsilastir: boolean;
};

export type Gorev = {
  adim: string;
  durum: "bekliyor" | "calisiyor" | "tamam" | "hata";
  tekrar_sayisi: number;
  hata_mesaji: string | null;
};

export type BelgeAyrintisi = {
  id: string;
  dava_dosyasi_id: string;
  orijinal_ad: string;
  mime_tur: string;
  sha256_ozet: string;
  sayfa_sayisi: number | null;
  durum: BelgeDurumu;
  yuklenme: string;
  sayfalar: SayfaOzeti[];
  gorevler: Gorev[];
};

export type Sayfa = {
  sayfa_no: number;
  metin: string;
  metin_kaynagi: "dogrudan" | "ocr";
  ocr_guven_skoru: number | null;
  asliyla_karsilastir: boolean;
  uyari: string | null;
};

export type MuvekkilTuru = "gercek_kisi" | "tuzel_kisi";

export type MuvekkilOzeti = {
  id: string;
  tur: MuvekkilTuru;
  ad_unvan: string;
  kimlik_no_maskeli: string | null;
  dava_sayisi: number;
  olusturma: string;
};

export type MuvekkilAyrintisi = {
  id: string;
  tur: MuvekkilTuru;
  ad_unvan: string;
  kimlik_no: string | null;
  iletisim: { telefon?: string; e_posta?: string; adres?: string };
  olusturma: string;
  davalar: { id: string; dosya_no: string; baslik: string; durum: Dava["durum"] }[];
};

export type ErisimRolu = "sorumlu" | "inceleyen";

export type Erisim = {
  kullanici_id: string;
  ad_soyad: string;
  rol: Kullanici["rol"];
  erisim_rolu: ErisimRolu;
  verilme: string;
};

export type BuroKullanicisi = { id: string; ad_soyad: string; rol: Kullanici["rol"] };

export function gonder<T>(yontem: "POST" | "PUT" | "PATCH" | "DELETE", yol: string, govde?: unknown): Promise<T> {
  return api<T>(yol, {
    method: yontem,
    headers: govde === undefined ? undefined : { "Content-Type": "application/json" },
    body: govde === undefined ? undefined : JSON.stringify(govde),
  });
}

export type BulguTuru = "tarih" | "tutar" | "kisi" | "kurum";
export type DogrulamaDurumu = "otomatik" | "inceleniyor" | "onaylandi" | "reddedildi";

export type AnalizBelgesi = {
  belge_id: string;
  orijinal_ad: string;
  belge_durumu: BelgeDurumu;
  ozel_nitelikli: boolean;
  ozel_nitelik_nedeni: string | null;
  ozel_nitelik_onayli: boolean;
  analiz_durumu: "calisiyor" | "tamam" | "hata" | null;
  analiz_baslangic: string | null;
  analiz_bitis: string | null;
  analiz_hatasi: string | null;
  bulgu_sayisi: number;
};

export type AnalizDurumu = {
  analiz_acik: boolean;
  model: string | null;
  karar_verebilir: boolean;
  belgeler: AnalizBelgesi[];
};

export type AnalizBaslatma = {
  baslatilan: { belge_id: string; orijinal_ad: string }[];
  onay_bekleyen: { belge_id: string; orijinal_ad: string }[];
  atlanan: { belge_id: string; orijinal_ad: string; neden: string }[];
};

export type Bulgu = {
  id: string;
  tur: BulguTuru;
  ozet: string;
  deger: string;
  yontem: "kural" | "model";
  guven_seviyesi: "dusuk" | "orta" | "yuksek";
  dogrulama_durumu: DogrulamaDurumu;
  belge_id: string;
  belge_adi: string;
  sayfa_no: number;
  metin_kaynagi: "dogrudan" | "ocr";
  ocr_guven_skoru: number | null;
  alinti_metni: string;
  karakter_baslangic: number | null;
  karakter_bitis: number | null;
  son_karar: "onay" | "red" | "duzeltme" | null;
  duzeltme_onceki: string | null; // avukat düzelttiyse ilk okunan değer (ör. "368.420,50 TL")
  son_not: string | null;
  inceleyen: string | null;
  etiket: string | null;          // ör. "dava değeri", "sözleşme tarihi"
  etiket_kaynak: "avukat" | null; // avukat seçtiyse otomatik etiket onu ezmez
  grup_anahtari: string;          // aynı değerin bulguları bu anahtarla tek satırda toplanır
};

export type CeliskiTarafi = {
  id: string;
  ozet: string;
  durum: DogrulamaDurumu;
  belge_id: string;
  belge_adi: string;
  sayfa_no: number;
  alinti: string;
  bas: number | null;
  bit: number | null;
};

export type CeliskiDurumu = "acik" | "incelendi" | "cozuldu";

export type Celiski = {
  id: string;
  tur: "tarih" | "tutar" | "kisi_kurum";
  aciklama: string;
  ciddiyet: "dusuk" | "orta" | "yuksek";
  durum: CeliskiDurumu;
  bulgu_1: CeliskiTarafi;
  bulgu_2: CeliskiTarafi;
};

export type OlayKaynagi = {
  id: string;
  ozet: string;
  etiket: string | null;
  belge_id: string;
  belge_adi: string;
  sayfa_no: number;
  alinti: string;
  bas: number | null;
  bit: number | null;
  dogrulama_durumu: DogrulamaDurumu;
};

export type Olay = {
  tarih: string;                  // YYYY-MM-DD, YYYY-MM ya da YYYY
  hassasiyet: "gun" | "ay" | "yil";
  ozet: string;
  etiketler: string[];
  kaynaklar: OlayKaynagi[];
  onayli: boolean;
  celiskili: boolean;
  onceki_olaydan_gun: number | null;
  celiski_aciklamalari: string[];
};

export type IddiaBagi = {
  tur: "ek_atfi" | "anilan_belge" | "ayni_deger" | "celiski";
  belge_id: string;
  belge_adi: string;
  aciklama: string;
  sayfa_no: number | null;        // yalnızca değer ve çelişki bağlarında
  bas: number | null;
  bit: number | null;
  alinti: string | null;
};

export type Iddia = {
  no: number;
  sayfa_no: number;
  bas: number;
  bit: number;
  metin: string;
  baglar: IddiaBagi[];
  dayanaksiz: boolean;
};

export type DelilKalemi = {
  metin: string;
  sayfa_no: number;
  bas: number;
  bit: number;
  tur: "dosyada" | "eksik" | "belge_disi" | "dis_kaynak";
  belgeler: { belge_id: string; belge_adi: string }[];
};

export type DilekceHaritasi = { belge_id: string; belge_adi: string; iddialar: Iddia[]; deliller: DelilKalemi[] };

export function kaynakAdresi(belgeId: string, sayfaNo: number, bas: number | null, bit: number | null): string {
  return `/belgeler/${belgeId}?sayfa=${sayfaNo}` + (bas !== null && bit !== null ? `&bas=${bas}&bit=${bit}` : "");
}

// --- Görünüm yardımcıları ---

export const BULGU_TURU: Record<BulguTuru, string> = {
  tarih: "Tarihler",
  tutar: "Tutarlar",
  kisi: "Kişiler",
  kurum: "Kurumlar",
};

export const DOGRULAMA: Record<DogrulamaDurumu, string> = {
  otomatik: "Otomatik",
  inceleniyor: "İnceleniyor",
  onaylandi: "Onaylandı",
  reddedildi: "Reddedildi",
};

export const MUVEKKIL_TURU: Record<MuvekkilTuru, string> = {
  gercek_kisi: "Gerçek kişi",
  tuzel_kisi: "Tüzel kişi",
};

export const ERISIM_ROLU: Record<ErisimRolu, string> = {
  sorumlu: "Sorumlu",
  inceleyen: "İnceleyen",
};

export function olusturabilir(kullanici: Kullanici): boolean {
  return kullanici.rol !== "stajyer";
}

export const BELGE_DURUMU: Record<BelgeDurumu, string> = {
  yuklendi: "Sırada",
  isleniyor: "İşleniyor",
  hazir: "Hazır",
  hata: "Hata",
};

export const DAVA_DURUMU: Record<Dava["durum"], string> = {
  acik: "Açık",
  kapali: "Kapalı",
  beklemede: "Beklemede",
};

export const ROL: Record<Kullanici["rol"], string> = {
  yonetici: "Yönetici",
  avukat: "Avukat",
  stajyer: "Stajyer",
};

export function tarih(deger: string): string {
  return new Date(deger).toLocaleString("tr-TR", { dateStyle: "medium", timeStyle: "short" });
}
