"use client";

// Belgeler arası çelişkiler: iki taraf yan yana, kaynaklarına bağlantılı; avukat inceler ya da çözer.

import Link from "next/link";
import { useState } from "react";
import { Celiski, CeliskiTarafi, DOGRULAMA, gonder, kaynakAdresi } from "@/lib/api";
import { CELISKI_DURUMU, CIDDIYET, DURUM_SINIFI, Islem } from "./ortak";

export default function CeliskiListesi({ celiskiler, kararVerebilir, islem, mesgul }: {
  celiskiler: Celiski[]; kararVerebilir: boolean; islem: Islem; mesgul: boolean;
}) {
  const [kapalilar, setKapalilar] = useState(false);
  const acik = celiskiler.filter((c) => c.durum === "acik");
  const gorunen = kapalilar ? celiskiler : acik;
  const durumYap = (c: Celiski, durum: Celiski["durum"]) =>
    islem(() => gonder("PUT", `/celiskiler/${c.id}`, { durum }));

  return (
    <div className="kart">
      <div className="baslik-satiri" style={{ marginBottom: 8 }}>
        <h2 style={{ margin: 0 }}>Belgeler arası çelişkiler <span className="ipucu">({acik.length} açık)</span></h2>
        {celiskiler.length > acik.length && (
          <button className="sade" onClick={() => setKapalilar((x) => !x)}>
            {kapalilar ? "Yalnızca açıkları göster" : `İncelenenleri de göster (${celiskiler.length - acik.length})`}
          </button>
        )}
      </div>
      {gorunen.length === 0 ? (
        <p className="ipucu">{celiskiler.length ? "Açık çelişki yok." : "Belgeler arasında çelişki bulunmadı."}</p>
      ) : gorunen.map((c) => (
        <div key={c.id} className={`celiski ${c.durum !== "acik" ? "kapali" : ""}`}>
          <div className="sag" style={{ justifyContent: "space-between" }}>
            <span>
              <span className={`rozet ${CIDDIYET[c.ciddiyet].sinif}`}>{CIDDIYET[c.ciddiyet].ad}</span>{" "}
              {c.durum !== "acik" && <span className="rozet soluk">{CELISKI_DURUMU[c.durum]}</span>}
            </span>
            {kararVerebilir && (
              <span className="sag">
                {c.durum !== "incelendi" && <button className="ikincil kucuk" disabled={mesgul} onClick={() => durumYap(c, "incelendi")}>İncelendi</button>}
                {c.durum !== "cozuldu" && <button className="ikincil kucuk" disabled={mesgul} onClick={() => durumYap(c, "cozuldu")}>Çözüldü</button>}
                {c.durum !== "acik" && <button className="sade kucuk" disabled={mesgul} onClick={() => durumYap(c, "acik")}>Yeniden aç</button>}
              </span>
            )}
          </div>
          <p style={{ margin: "6px 0" }}>{c.aciklama}</p>
          <div className="celiski-taraflar">
            <Taraf t={c.bulgu_1} />
            <span className="celiski-ayrac" aria-hidden>≠</span>
            <Taraf t={c.bulgu_2} />
          </div>
        </div>
      ))}
      <p className="ipucu">
        Çelişkiler metindeki etiketlere bakılarak otomatik işaretlenir (ör. iki belgede farklı &quot;dava değeri&quot;).
        Hatalı bir bulguyu reddetmek, ona bağlı çelişkiyi de kaldırır.
      </p>
    </div>
  );
}

function Taraf({ t }: { t: CeliskiTarafi }) {
  return (
    <div className="celiski-taraf">
      <strong>{t.ozet}</strong>
      <div className="ipucu">
        <Link href={kaynakAdresi(t.belge_id, t.sayfa_no, t.bas, t.bit)}>{t.belge_adi}</Link> · s. {t.sayfa_no}
        {t.durum !== "otomatik" && <> · <span className={`rozet ${DURUM_SINIFI[t.durum]}`}>{DOGRULAMA[t.durum]}</span></>}
      </div>
      <div className="alinti-kucuk">“{t.alinti}”</div>
    </div>
  );
}
