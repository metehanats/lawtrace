"use client";

// Dava sayfası sekmelerinin ortak verisi ve yardımcıları. Sayfa tüm veriyi bir kez yükler;
// sekmeler aynı veriyi gösterir, bir sekmedeki karar (ör. bulgu onayı) diğerlerine de yansır.

import { useCallback, useEffect, useState } from "react";
import { useOturumHatasi } from "@/components/Korumali";
import {
  AnalizDurumu, api, ApiHatasi, BelgeListesi, Bulgu, BulguTuru, Celiski, CeliskiDurumu, Dava, DilekceHaritasi,
  DogrulamaDurumu, Olay,
} from "@/lib/api";

const YENILEME_MS = 3500;

export const TURLER: BulguTuru[] = ["tarih", "tutar", "kisi", "kurum"];
export const CIDDIYET: Record<Celiski["ciddiyet"], { ad: string; sinif: string }> = {
  yuksek: { ad: "Yüksek", sinif: "hata" },
  orta: { ad: "Orta", sinif: "uyari" },
  dusuk: { ad: "Düşük", sinif: "soluk" },
};
export const CELISKI_DURUMU: Record<CeliskiDurumu, string> = { acik: "Açık", incelendi: "İncelendi", cozuldu: "Çözüldü" };
export const DURUM_SINIFI: Record<DogrulamaDurumu, string> = {
  otomatik: "soluk", inceleniyor: "", onaylandi: "hazir", reddedildi: "hata",
};

export type DavaVerisi = {
  dava: Dava | null;
  belgeler: BelgeListesi | null;
  analiz: AnalizDurumu | null;
  bulgular: Bulgu[] | null;
  celiskiler: Celiski[];
  olaylar: Olay[];
  harita: DilekceHaritasi[];
};

/** Dava sayfasının tüm verisi. İşlenen belge ya da süren analiz varken kendiliğinden yenilenir. */
export function useDavaVerisi(davaId: string) {
  const oturumHatasi = useOturumHatasi();
  const [veri, setVeri] = useState<DavaVerisi>({
    dava: null, belgeler: null, analiz: null, bulgular: null, celiskiler: [], olaylar: [], harita: [],
  });
  const [hata, setHata] = useState<string | null>(null);

  const yukle = useCallback(async () => {
    try {
      const [dava, belgeler, analiz, b, c, o, h] = await Promise.all([
        api<Dava>(`/davalar/${davaId}`),
        api<BelgeListesi>(`/davalar/${davaId}/belgeler?limit=200`),
        api<AnalizDurumu>(`/davalar/${davaId}/analiz`),
        api<{ bulgular: Bulgu[] }>(`/davalar/${davaId}/bulgular`),
        api<{ celiskiler: Celiski[] }>(`/davalar/${davaId}/celiskiler`),
        api<{ olaylar: Olay[] }>(`/davalar/${davaId}/zaman-cizelgesi`),
        api<{ dilekceler: DilekceHaritasi[] }>(`/davalar/${davaId}/iddia-haritasi`),
      ]);
      setVeri({ dava, belgeler, analiz, bulgular: b.bulgular, celiskiler: c.celiskiler, olaylar: o.olaylar,
                harita: h.dilekceler });
      setHata(null);
    } catch (h) {
      if (!oturumHatasi(h)) setHata(h instanceof Error ? h.message : "Yüklenemedi.");
    }
  }, [davaId, oturumHatasi]);

  useEffect(() => {
    yukle();
  }, [yukle]);

  const surenIs = Boolean(
    veri.belgeler?.belgeler.some((b) => b.durum === "yuklendi" || b.durum === "isleniyor") ||
    veri.analiz?.belgeler.some((b) => b.analiz_durumu === "calisiyor"),
  );
  useEffect(() => {
    if (!surenIs) return;
    const z = setInterval(yukle, YENILEME_MS);
    return () => clearInterval(z);
  }, [surenIs, yukle]);

  return { ...veri, hata, yukle, surenIs };
}

export type Bildirim = { tur: "hata" | "basari" | "uyari"; mesaj: string } | null;
export type Islem = <T>(fn: () => Promise<T>, basari?: (v: T) => string | null) => Promise<T | undefined>;

/** Sunucuya yazan işlemler: meşgul durumu, sonuç bildirimi ve ardından verinin yenilenmesi. */
export function useIslem(yukle: () => Promise<void>) {
  const oturumHatasi = useOturumHatasi();
  const [mesgul, setMesgul] = useState(false);
  const [bildirim, setBildirim] = useState<Bildirim>(null);

  const islem: Islem = useCallback(async (fn, basari) => {
    setBildirim(null);
    setMesgul(true);
    try {
      const sonuc = await fn();
      const mesaj = basari?.(sonuc);
      if (mesaj) setBildirim({ tur: "basari", mesaj });
      await yukle();
      return sonuc;
    } catch (h) {
      if (!oturumHatasi(h)) setBildirim({ tur: "hata", mesaj: h instanceof ApiHatasi ? h.message : "İşlem yapılamadı." });
      return undefined;
    } finally {
      setMesgul(false);
    }
  }, [yukle, oturumHatasi]);

  return { islem, mesgul, bildirim, setBildirim };
}

/** Açık çelişkiye karışan bulgu kimlikleri. */
export function celiskiliBulgular(celiskiler: Celiski[]): Map<string, Celiski[]> {
  const harita = new Map<string, Celiski[]>();
  for (const c of celiskiler) {
    if (c.durum !== "acik") continue;
    for (const id of [c.bulgu_1.id, c.bulgu_2.id]) harita.set(id, [...(harita.get(id) ?? []), c]);
  }
  return harita;
}

export function ocrSupheli(b: Bulgu): boolean {
  return b.metin_kaynagi === "ocr" && (b.ocr_guven_skoru === null || b.ocr_guven_skoru < 0.93);
}
