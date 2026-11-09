"use client";

// Girişten hemen sonra, sayfa yüklenirken gösterilen karşılama: kullanıcının rol simgesi
// (yönetici taç, avukat kravat, stajyer sırt çantası) madeni para gibi döner.
// Giriş sayfası rolü sessionStorage'a yazar; korumalı sayfa yüklenirken aynı ekranı sürdürür,
// kullanıcı yüklenince siler. Böylece giriş → sayfa geçişi tek, kesintisiz bir ekran olur.

import { Simge } from "@/components/Simgeler";
import { Kullanici, ROL } from "@/lib/api";

const ANAHTAR = "hosgeldiniz";
export const EN_AZ_SURE_MS = 900; // sayfa çok hızlı yüklense de simge görülebilsin

export type Karsilama = { rol: Kullanici["rol"]; ad: string };

export function karsilamaKaydet(k: Karsilama) {
  try {
    sessionStorage.setItem(ANAHTAR, JSON.stringify(k));
  } catch {
    // depolama kapalıysa karşılama yalnızca giriş sayfasında görünür
  }
}

export function karsilamaOku(): Karsilama | null {
  try {
    const k = JSON.parse(sessionStorage.getItem(ANAHTAR) ?? "null");
    return k && k.rol in ROL ? k : null;
  } catch {
    return null;
  }
}

export function karsilamaSil() {
  try {
    sessionStorage.removeItem(ANAHTAR);
  } catch {
    // yok say
  }
}

export default function HosGeldiniz({ rol, ad }: Karsilama) {
  return (
    <main className="hosgeldiniz" role="status" aria-live="polite">
      <div className="hosgeldiniz-simge">
        <span className="donen"><Simge ad={rol} boyut={56} /></span>
      </div>
      <div className="hosgeldiniz-ad">Hoş geldiniz, {ad}</div>
      <div className="ipucu">{ROL[rol]} · dosyalarınız hazırlanıyor…</div>
    </main>
  );
}
