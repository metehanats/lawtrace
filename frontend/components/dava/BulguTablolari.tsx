"use client";

// Değere göre gruplanmış bulgular: aynı değer farklı kaynaklarda tek satırda. Toplu ya da kaynak
// başına karar. Tek tek, kaynağıyla yan yana incelemek için "İncelemeye başla".

import Link from "next/link";
import { useState } from "react";
import { Simge } from "@/components/Simgeler";
import { Bulgu, BULGU_TURU, BulguTuru, Celiski, DOGRULAMA, gonder, kaynakAdresi } from "@/lib/api";
import { celiskiliBulgular, DURUM_SINIFI, Islem, ocrSupheli, TURLER } from "./ortak";

type Grup = { anahtar: string; tur: BulguTuru; ozet: string; etiketler: string[]; bulgular: Bulgu[] };

function grupla(bulgular: Bulgu[]): Grup[] {
  const gruplar = new Map<string, Grup>();
  for (const b of bulgular) {
    const g = gruplar.get(b.grup_anahtari) ??
      { anahtar: b.grup_anahtari, tur: b.tur, ozet: b.ozet, etiketler: [], bulgular: [] };
    g.bulgular.push(b);
    if (b.etiket && !g.etiketler.includes(b.etiket)) g.etiketler.push(b.etiket);
    gruplar.set(b.grup_anahtari, g);
  }
  return [...gruplar.values()];
}

export default function BulguTablolari({ bulgular, celiskiler, kararVerebilir, islem, mesgul, incele }: {
  bulgular: Bulgu[]; celiskiler: Celiski[]; kararVerebilir: boolean; islem: Islem; mesgul: boolean;
  incele: () => void;
}) {
  const [suzgec, setSuzgec] = useState<"hepsi" | "incelenmemis" | "celiskili">("hepsi");
  const celiskili = celiskiliBulgular(celiskiler);
  const otomatik = bulgular.filter((b) => b.dogrulama_durumu === "otomatik").length;
  const gruplar = grupla(bulgular).filter((g) =>
    suzgec === "hepsi" ||
    (suzgec === "incelenmemis" && g.bulgular.some((b) => b.dogrulama_durumu === "otomatik")) ||
    (suzgec === "celiskili" && g.bulgular.some((b) => celiskili.has(b.id))));

  const karar = (b: Bulgu, k: "onay" | "red") => gonder("POST", `/bulgular/${b.id}/inceleme`, { karar: k });
  const toplu = (g: Grup, k: "onay" | "red") => islem(async () => {
    const hedef = k === "onay" ? "onaylandi" : "reddedildi";
    for (const b of g.bulgular) if (b.dogrulama_durumu !== hedef) await karar(b, k);
  });

  if (bulgular.length === 0) {
    return <div className="kart"><p className="ipucu" style={{ margin: 0 }}>Henüz bulgu yok. Analiz bittiğinde burada görünür.</p></div>;
  }

  return (
    <div className="kart">
      <div className="baslik-satiri" style={{ marginBottom: 8 }}>
        <div>
          <h2 style={{ margin: 0 }}>Bulgular</h2>
          <p className="ipucu" style={{ margin: 0 }}>
            {bulgular.length} bulgu · {otomatik > 0 ? <strong>{otomatik} incelenmemiş</strong> : "hepsi incelendi"}
          </p>
        </div>
        <div className="sag">
          <label htmlFor="suzgec" style={{ margin: 0 }}>Göster:</label>
          <select id="suzgec" value={suzgec} onChange={(o) => setSuzgec(o.target.value as typeof suzgec)} style={{ width: "auto" }}>
            <option value="hepsi">Tümü</option>
            <option value="incelenmemis">İncelenmemiş olanlar</option>
            <option value="celiskili">Çelişkiye karışanlar</option>
          </select>
          {kararVerebilir && (
            <button onClick={incele}><Simge ad="bulgular" />{otomatik > 0 ? "İncelemeye başla" : "Kaynaklarıyla gözden geçir"}</button>
          )}
        </div>
      </div>
      <div className="bildirim uyari" style={{ marginTop: 0 }}>
        Bulgular otomatik çıkarılmıştır ve avukat onayı olmadan kesin bilgi değildir. Her bulguyu kaynağıyla karşılaştırın.
      </div>
      {TURLER.map((tur) => {
        const turGruplari = gruplar.filter((g) => g.tur === tur);
        if (!turGruplari.length) return null;
        return (
          <div key={tur} className="tablo-kap" style={{ marginTop: 14 }}>
            <h3 className="grup-baslik">{BULGU_TURU[tur]} <span className="ipucu">({turGruplari.length})</span></h3>
            <table>
              <thead><tr><th>Değer</th><th>Kaynaklar</th>{kararVerebilir && <th />}</tr></thead>
              <tbody>
                {turGruplari.map((g) => (
                  <GrupSatiri key={g.anahtar} g={g} celiskili={g.bulgular.some((b) => celiskili.has(b.id))}
                              kararVerebilir={kararVerebilir} mesgul={mesgul}
                              tekKarar={(b, k) => islem(() => karar(b, k))} topluKarar={(k) => toplu(g, k)} />
                ))}
              </tbody>
            </table>
          </div>
        );
      })}
    </div>
  );
}

function GrupSatiri({ g, celiskili, kararVerebilir, mesgul, tekKarar, topluKarar }: {
  g: Grup; celiskili: boolean; kararVerebilir: boolean; mesgul: boolean;
  tekKarar: (b: Bulgu, k: "onay" | "red") => void; topluKarar: (k: "onay" | "red") => void;
}) {
  const hepsiReddedildi = g.bulgular.every((b) => b.dogrulama_durumu === "reddedildi");
  return (
    <tr style={hepsiReddedildi ? { opacity: 0.6 } : undefined}>
      <td style={{ minWidth: 150 }}>
        <strong>{g.ozet}</strong>
        {celiskili && <div><span className="rozet hata" title="Bu değer açık bir çelişkiye karışıyor">⚠ Çelişki</span></div>}
        {g.etiketler.length > 0 && <div className="ipucu">{g.etiketler.join(", ")}</div>}
        <div className="ipucu">{g.bulgular.length} kaynak</div>
      </td>
      <td>
        <ul className="kaynak-listesi">
          {g.bulgular.map((b) => (
            <li key={b.id} style={b.dogrulama_durumu === "reddedildi" ? { opacity: 0.6 } : undefined}>
              <div className="sag" style={{ gap: 6 }}>
                <Link href={kaynakAdresi(b.belge_id, b.sayfa_no, b.karakter_baslangic, b.karakter_bitis)}>{b.belge_adi}</Link>
                <span className="ipucu">s. {b.sayfa_no} · {b.yontem === "kural" ? "Kural" : "Model"}</span>
                {ocrSupheli(b) && <span className="rozet uyari">⚠ OCR</span>}
                <span className={`rozet ${DURUM_SINIFI[b.dogrulama_durumu]}`}>{DOGRULAMA[b.dogrulama_durumu]}</span>
                {b.duzeltme_onceki && <span className="ipucu">düzeltildi (ilk okunan: <s>{b.duzeltme_onceki}</s>)</span>}
                {kararVerebilir && g.bulgular.length > 1 && (
                  <>
                    {b.dogrulama_durumu !== "onaylandi" && (
                      <button className="sade kucuk" disabled={mesgul} onClick={() => tekKarar(b, "onay")}
                              title="Yalnızca bu kaynağı onayla" aria-label="Yalnızca bu kaynağı onayla">
                        <Simge ad="onayla" boyut={15} />
                      </button>
                    )}
                    {b.dogrulama_durumu !== "reddedildi" && (
                      <button className="sade kucuk" disabled={mesgul} onClick={() => tekKarar(b, "red")}
                              title="Yalnızca bu kaynağı reddet" aria-label="Yalnızca bu kaynağı reddet">
                        <Simge ad="reddet" boyut={15} />
                      </button>
                    )}
                  </>
                )}
              </div>
              <div className="alinti-kucuk">“{b.alinti_metni}”</div>
              {b.inceleyen && <div className="ipucu">{b.inceleyen}{b.son_not ? `: ${b.son_not}` : ""}</div>}
            </li>
          ))}
        </ul>
      </td>
      {kararVerebilir && (
        <td style={{ whiteSpace: "nowrap", textAlign: "right" }}>
          {g.bulgular.some((b) => b.dogrulama_durumu !== "onaylandi") && (
            <button className="ikincil kucuk" disabled={mesgul} onClick={() => topluKarar("onay")}>
              <Simge ad="onayla" boyut={15} />{g.bulgular.length > 1 ? "Tümünü onayla" : "Onayla"}
            </button>
          )}{" "}
          {g.bulgular.some((b) => b.dogrulama_durumu !== "reddedildi") && (
            <button className="tehlike kucuk" disabled={mesgul} onClick={() => topluKarar("red")}>
              <Simge ad="reddet" boyut={15} />{g.bulgular.length > 1 ? "Tümünü reddet" : "Reddet"}
            </button>
          )}
        </td>
      )}
    </tr>
  );
}
