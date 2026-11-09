"use client";

// Kullanıcının kendi parolasını değiştirdiği form. Geçici parolayla giren kullanıcıya zorunlu
// olarak gösterilir (Korumali); ayrıca /parola sayfasından da açılır.

import { FormEvent, useState } from "react";
import { ApiHatasi, gonder, OturumYok } from "@/lib/api";

export default function ParolaDegistir({ zorunlu, bitti }: { zorunlu: boolean; bitti: () => void }) {
  const [mevcut, setMevcut] = useState("");
  const [yeni, setYeni] = useState("");
  const [tekrar, setTekrar] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  async function kaydet(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    if (yeni !== tekrar) {
      setHata("Yeni parola ile tekrarı aynı değil.");
      return;
    }
    setGonderiliyor(true);
    try {
      await gonder("POST", "/oturum/parola", { mevcut, yeni });
      bitti();
    } catch (h) {
      if (h instanceof OturumYok) {
        // Çok sayıda hatalı "mevcut parola": sunucu hesabı kilitledi ve tüm oturumları kapattı
        window.location.replace("/giris?kilit=1");
        return;
      }
      setHata(h instanceof ApiHatasi ? h.message : "Parola değiştirilemedi.");
      setGonderiliyor(false);
    }
  }

  return (
    <form className="kart form-kart" onSubmit={kaydet} style={{ maxWidth: 460 }}>
      <h1>{zorunlu ? "Parolanızı belirleyin" : "Parolamı değiştir"}</h1>
      <p className="alt-baslik">
        {zorunlu
          ? "Hesabınız geçici bir parolayla açıldı. Devam etmek için kendi parolanızı belirleyin."
          : "Değişiklikten sonra diğer cihazlardaki oturumlarınız kapanır."}
      </p>
      {hata && <div className="bildirim hata" role="alert">{hata}</div>}
      <label htmlFor="mevcut">{zorunlu ? "Geçici parola" : "Mevcut parola"}</label>
      <input id="mevcut" type="password" autoComplete="current-password" required value={mevcut}
             onChange={(o) => setMevcut(o.target.value)} />
      <label htmlFor="yeni">Yeni parola</label>
      <input id="yeni" type="password" autoComplete="new-password" required minLength={12} value={yeni}
             onChange={(o) => setYeni(o.target.value)} />
      <div className="ipucu">En az 12 karakter; e-posta adınızı içermemeli.</div>
      <label htmlFor="tekrar">Yeni parola (tekrar)</label>
      <input id="tekrar" type="password" autoComplete="new-password" required value={tekrar}
             onChange={(o) => setTekrar(o.target.value)} />
      <div className="form-dugmeler">
        <button type="submit" disabled={gonderiliyor}>{gonderiliyor ? "Kaydediliyor…" : "Parolayı kaydet"}</button>
      </div>
    </form>
  );
}
