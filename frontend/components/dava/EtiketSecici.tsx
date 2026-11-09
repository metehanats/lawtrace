"use client";

// Tarih/tutar bulgusunun etiketini avukat seçer ("dava değeri", "fesih tarihi"…) ya da kendi
// etiketini yazar ("hasar bedeli"). Çelişki tespiti bu etikete bakar: iki belgede aynı etiketle
// farklı değer varsa çelişkidir. Avukatın seçimi otomatik etiketle ezilmez.

import { FormEvent, forwardRef, useState } from "react";
import { Bulgu, gonder } from "@/lib/api";
import type { Islem } from "./ortak";

const ETIKETSIZ = "";
const DIGER = "__diger";

type Ozellik = { bulgu: Bulgu; secenekler: string[]; islem: Islem; mesgul: boolean };

const EtiketSecici = forwardRef<HTMLSelectElement, Ozellik>(function EtiketSecici(
  { bulgu, secenekler, islem, mesgul }, ref,
) {
  const [serbest, setSerbest] = useState<string | null>(null);
  const liste = bulgu.etiket && !secenekler.includes(bulgu.etiket) ? [bulgu.etiket, ...secenekler] : secenekler;

  // Bildirimde sunucunun kaydettiği (sadeleştirilmiş) etiket gösterilir
  const kaydet = (etiket: string | null) =>
    islem(() => gonder<{ etiket: string | null }>("PUT", `/bulgular/${bulgu.id}/etiket`, { etiket }),
          (v) => (v.etiket ? `Etiket: ${v.etiket}` : "Etiket kaldırıldı."));

  function serbestKaydet(olay: FormEvent) {
    olay.preventDefault();
    if (serbest && serbest.trim().length >= 2) {
      kaydet(serbest);
      setSerbest(null);
    }
  }

  return (
    <div className="etiket-secici">
      <label htmlFor="etiket-sec" style={{ margin: 0 }}>Etiket <span className="kisayol">E</span></label>
      <select id="etiket-sec" ref={ref} disabled={mesgul} value={serbest !== null ? DIGER : bulgu.etiket ?? ETIKETSIZ}
              style={{ width: "auto", minWidth: 180 }}
              onChange={(o) => {
                const v = o.target.value;
                if (v === DIGER) setSerbest("");
                else { setSerbest(null); kaydet(v === ETIKETSIZ ? null : v); }
              }}>
        <option value={ETIKETSIZ}>— etiketsiz —</option>
        {liste.map((e) => <option key={e} value={e}>{e}</option>)}
        <option value={DIGER}>Diğer… (kendiniz yazın)</option>
      </select>
      {serbest !== null ? (
        <form className="sag" onSubmit={serbestKaydet} onKeyDown={(o) => { if (o.key === "Escape") setSerbest(null); }}>
          <input type="text" autoFocus value={serbest} maxLength={40} placeholder="ör. hasar bedeli"
                 onChange={(o) => setSerbest(o.target.value)} style={{ width: 200 }} />
          <button type="submit" className="kucuk" disabled={mesgul || serbest.trim().length < 2}>Kaydet</button>
        </form>
      ) : (
        <span className="ipucu">
          {bulgu.etiket_kaynak === "avukat" ? "siz seçtiniz" : bulgu.etiket ? "otomatik bulundu" : "aynı etiketle farklı değerler çelişki sayılır"}
        </span>
      )}
    </div>
  );
});

export default EtiketSecici;
