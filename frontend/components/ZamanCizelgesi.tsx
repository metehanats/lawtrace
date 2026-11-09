"use client";

// Dava dosyasının zaman çizelgesi: bulunan tarihler kronolojik sırada, her olay kaynağıyla.
// Olay adı yalnızca metindeki etiketten gelir; etiketsiz tarihte avukat alıntıyı okur.

import Link from "next/link";
import { useState } from "react";
import { kaynakAdresi, Olay } from "@/lib/api";

const AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim",
  "Kasım", "Aralık"];

// Saat dilimine takılmamak için Date kullanılmaz: "2024-11-03" → "3 Kasım 2024"
export function olayTarihi(deger: string): string {
  const [yil, ay, gun] = deger.split("-");
  if (gun) return `${Number(gun)} ${AYLAR[Number(ay) - 1]} ${yil}`;
  if (ay) return `${AYLAR[Number(ay) - 1]} ${yil}`;
  return yil;
}

function aralik(gun: number): string {
  if (gun < 60) return `${gun} gün sonra`;
  const ay = Math.round(gun / 30.44);
  return ay < 24 ? `${gun} gün (~${ay} ay) sonra` : `${gun} gün (~${Math.round(gun / 365.25)} yıl) sonra`;
}

const buyukHarf = (s: string) => s.toLocaleUpperCase("tr-TR").slice(0, 1) + s.slice(1);

export default function ZamanCizelgesi({ olaylar }: { olaylar: Olay[] }) {
  const [yalnizEtiketli, setYalnizEtiketli] = useState(false);
  const etiketliSayisi = olaylar.filter((o) => o.etiketler.length).length;
  const gorunen = yalnizEtiketli ? olaylar.filter((o) => o.etiketler.length) : olaylar;

  return (
    <section aria-label="Zaman çizelgesi" style={{ marginTop: 14 }}>
      <div className="baslik-satiri" style={{ margin: "0 0 6px" }}>
        <h3 className="grup-baslik" style={{ margin: 0 }}>
          Zaman çizelgesi <span className="ipucu">({olaylar.length} tarih)</span>
        </h3>
        {etiketliSayisi > 0 && etiketliSayisi < olaylar.length && (
          <label className="sag" style={{ margin: 0, fontWeight: 500 }}>
            <input type="checkbox" checked={yalnizEtiketli} onChange={(o) => setYalnizEtiketli(o.target.checked)} />
            Yalnızca adı belli olaylar ({etiketliSayisi})
          </label>
        )}
      </div>
      <ol className="cizelge">
        {gorunen.map((o, i) => (
          <li key={o.tarih} className={`cizelge-olay ${o.celiskili ? "celiskili" : ""}`}>
            {/* Süzgeç açıkken aradaki olaylar gizli olabilir; gün farkı yalnızca tam listede anlamlı */}
            {!yalnizEtiketli && i > 0 && o.onceki_olaydan_gun !== null && (
              <div className="cizelge-aralik">{aralik(o.onceki_olaydan_gun)}</div>
            )}
            <div className="cizelge-baslik">
              <strong>{olayTarihi(o.tarih)}</strong>
              {o.hassasiyet !== "gun" && (
                <span className="rozet soluk" title="Metinde gün belirtilmemiş">
                  {o.hassasiyet === "ay" ? "yalnızca ay" : "yalnızca yıl"}
                </span>
              )}
              {o.etiketler.map((e) => <span key={e} className="rozet">{buyukHarf(e)}</span>)}
              {o.celiskili && <span className="rozet hata">Çelişkili</span>}
              {o.onayli && <span className="rozet hazir">Onaylandı</span>}
            </div>
            {o.celiski_aciklamalari.map((a) => <div key={a} className="ipucu">{a}</div>)}
            <ul className="kaynak-listesi">
              {o.kaynaklar.map((k) => (
                <li key={k.id}>
                  <span className="ipucu">
                    <Link href={kaynakAdresi(k.belge_id, k.sayfa_no, k.bas, k.bit)}>{k.belge_adi}</Link> · s. {k.sayfa_no}
                  </span>
                  <div className="alinti-kucuk">“{k.alinti}”</div>
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
      <p className="ipucu">
        Tarihler otomatik çıkarılmıştır; olay adı metindeki etiketten gelir. Reddedilen tarihler çizelgede gösterilmez.
      </p>
    </section>
  );
}
