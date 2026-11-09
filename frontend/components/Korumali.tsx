"use client";

// Oturum gerektiren sayfaların çerçevesi: kullanıcıyı yükler, oturum yoksa giriş sayfasına
// yönlendirir ve üst çubuğu (büro, kullanıcı, çıkış) gösterir.

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useState } from "react";
import HosGeldiniz, { Karsilama, karsilamaOku, karsilamaSil } from "@/components/HosGeldiniz";
import ParolaDegistir from "@/components/ParolaDegistir";
import { Rol, Simge } from "@/components/Simgeler";
import TemaAnahtari from "@/components/TemaAnahtari";
import { api, Kullanici, OturumYok } from "@/lib/api";

const KullaniciBaglami = createContext<Kullanici | null>(null);

export function useKullanici(): Kullanici {
  const kullanici = useContext(KullaniciBaglami);
  if (!kullanici) throw new Error("useKullanici yalnızca <Korumali> içinde kullanılabilir.");
  return kullanici;
}

/** Oturum düşerse giriş sayfasına gönderen hata işleyici. */
export function useOturumHatasi() {
  const router = useRouter();
  const yol = usePathname();
  return useCallback(
    (hata: unknown): boolean => {
      if (hata instanceof OturumYok) {
        router.replace(`/giris?donus=${encodeURIComponent(yol)}`);
        return true;
      }
      return false;
    },
    [router, yol],
  );
}

export default function Korumali({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const yol = usePathname();
  const oturumHatasi = useOturumHatasi();
  const [kullanici, setKullanici] = useState<Kullanici | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  // Girişten yeni gelindiyse karşılama ekranı sayfa yüklenene kadar sürer (bkz. HosGeldiniz).
  // Boyamadan önce okunur: arada bir an "Yükleniyor…" görünmesin.
  const [karsilama, setKarsilama] = useState<Karsilama | null>(null);
  useLayoutEffect(() => setKarsilama(karsilamaOku()), []);

  const yukle = useCallback(() => {
    api<Kullanici>("/oturum/ben")
      .then((k) => {
        setKullanici(k);
        karsilamaSil();
      })
      .catch((h) => {
        karsilamaSil();
        if (!oturumHatasi(h)) setHata(h instanceof Error ? h.message : "Bağlantı kurulamadı.");
      });
  }, [oturumHatasi]);

  useEffect(yukle, [yukle]);

  async function cikis() {
    try {
      await api<void>("/oturum/cikis", { method: "POST" });
    } finally {
      router.replace("/giris");
    }
  }

  if (hata) {
    return (
      <main className="kap">
        <div className="bildirim hata">Sunucuya ulaşılamadı: {hata}</div>
      </main>
    );
  }
  if (!kullanici) return karsilama ? <HosGeldiniz {...karsilama} /> : <main className="kap ipucu">Yükleniyor…</main>;

  return (
    <KullaniciBaglami.Provider value={kullanici}>
      <header className="ust">
        <div className="ust-ic">
          <nav className="gezinme" aria-label="Ana menü">
            <Link href="/davalar" className="marka">
              <Simge ad="marka" boyut={22} />
              <span className="marka-ad">Law<span>Trace</span></span>
            </Link>
            <Link href="/davalar" aria-current={yol.startsWith("/davalar") || yol.startsWith("/belgeler")}>
              <Simge ad="davalar" />Dava dosyaları
            </Link>
            <Link href="/muvekkiller" aria-current={yol.startsWith("/muvekkiller")}>
              <Simge ad="muvekkiller" />Müvekkiller
            </Link>
            {kullanici.rol === "yonetici" && (
              <Link href="/yonetim" aria-current={yol.startsWith("/yonetim")}>
                <Simge ad="yonetim" />Yönetim
              </Link>
            )}
          </nav>
          <div className="kisi">
            <span title={`${kullanici.buro_adi} · ${kullanici.e_posta}`}>
              <strong>{kullanici.ad_soyad}</strong> · <Rol rol={kullanici.rol} />
            </span>
            <TemaAnahtari />
            <Link href="/parola" className="sade" title="Parolamı değiştir">
              <Simge ad="parola" />Parola
            </Link>
            <button className="sade" onClick={cikis}>
              <Simge ad="cikis" />Çıkış
            </button>
          </div>
        </div>
      </header>
      <main className="kap">
        {/* Geçici parolayla girildiyse hangi sayfa açılırsa açılsın önce parola belirlenir */}
        {kullanici.parola_degismeli ? <ParolaDegistir zorunlu bitti={yukle} /> : children}
      </main>
    </KullaniciBaglami.Provider>
  );
}
