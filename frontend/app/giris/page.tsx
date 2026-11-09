"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useState } from "react";
import HosGeldiniz, { EN_AZ_SURE_MS, Karsilama, karsilamaKaydet } from "@/components/HosGeldiniz";
import { ApiHatasi, jsonGonder, Kullanici } from "@/lib/api";

function GirisFormu() {
  const router = useRouter();
  const parametreler = useSearchParams();
  const [ePosta, setEPosta] = useState("");
  const [parola, setParola] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [karsilama, setKarsilama] = useState<Karsilama | null>(null);

  async function gonder(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    setGonderiliyor(true);
    try {
      const { kullanici } = await jsonGonder<{ kullanici: Kullanici }>("/oturum/giris", { e_posta: ePosta, parola });
      // Karşılama: rol simgesi dönerken hedef sayfa yüklenir (korumalı sayfa aynı ekranı sürdürür)
      const k = { rol: kullanici.rol, ad: kullanici.ad_soyad };
      karsilamaKaydet(k);
      setKarsilama(k);
      await new Promise((r) => setTimeout(r, EN_AZ_SURE_MS));
      // Yalnızca site içi dönüş adreslerine izin verilir (açık yönlendirmeyi önler)
      const donus = parametreler.get("donus");
      router.replace(donus && donus.startsWith("/") && !donus.startsWith("//") ? donus : "/davalar");
    } catch (h) {
      setHata(h instanceof ApiHatasi ? h.message : "Sunucuya ulaşılamadı.");
      setParola("");
    } finally {
      setGonderiliyor(false);
    }
  }

  if (karsilama) return <HosGeldiniz {...karsilama} />;

  return (
    <main className="giris-sayfa">
      <form className="kart giris-kart" onSubmit={gonder}>
        <h1>Giriş yap</h1>
        <p className="alt-baslik">LawTrace · Her bulgunun izi belgesinde.</p>
        {hata && (
          <div className="bildirim hata" role="alert">
            {hata}
          </div>
        )}
        {!hata && parametreler.get("kilit") === "1" && (
          <div className="bildirim uyari" role="alert">
            Çok sayıda hatalı parola denemesi nedeniyle hesabınız geçici olarak kilitlendi ve tüm oturumlarınız
            kapatıldı. Bir süre sonra yeniden deneyin ya da büro yöneticinizden kilidi açmasını isteyin.
          </div>
        )}
        <label htmlFor="e_posta">E-posta</label>
        <input
          id="e_posta"
          type="email"
          autoComplete="username"
          required
          value={ePosta}
          onChange={(o) => setEPosta(o.target.value)}
        />
        <label htmlFor="parola">Parola</label>
        <input
          id="parola"
          type="password"
          autoComplete="current-password"
          required
          value={parola}
          onChange={(o) => setParola(o.target.value)}
        />
        <button type="submit" disabled={gonderiliyor}>
          {gonderiliyor ? "Giriş yapılıyor…" : "Giriş yap"}
        </button>
      </form>
    </main>
  );
}

export default function GirisSayfasi() {
  return (
    <Suspense>
      <GirisFormu />
    </Suspense>
  );
}
