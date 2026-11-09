"use client";

// Belgeler sekmesi: sürükle-bırak ya da seçerek yükleme ve dosyadaki belgelerin listesi.

import Link from "next/link";
import { DragEvent, useRef, useState } from "react";
import { BelgeDurumRozeti } from "@/components/Durum";
import { useOturumHatasi } from "@/components/Korumali";
import { Simge } from "@/components/Simgeler";
import { api, ApiHatasi, BelgeListesi, tarih } from "@/lib/api";

export default function BelgelerSekmesi({ davaId, liste, yuklendi, kapali }: {
  davaId: string; liste: BelgeListesi; yuklendi: () => void; kapali: boolean;
}) {
  return (
    <>
      {!kapali && <><BelgeYukle davaId={davaId} yuklendi={yuklendi} /><div className="bosluk" /></>}
      <div className="kart tablo-kap">
        <h2>Belgeler <span className="ipucu">({liste.toplam})</span></h2>
        {liste.belgeler.length === 0 ? (
          <p className="ipucu">
            Bu dosyada henüz belge yok.{!kapali && " Yukarıdaki alana sürükleyerek ekleyebilirsiniz."}
          </p>
        ) : (
          <table>
            <thead>
              <tr><th>Belge</th><th>Durum</th><th className="sayi">Sayfa</th><th>OCR</th><th>Yüklenme</th></tr>
            </thead>
            <tbody>
              {liste.belgeler.map((b) => (
                <tr key={b.id}>
                  <td>
                    <Link href={`/belgeler/${b.id}`}>{b.orijinal_ad}</Link>
                    <div className="ipucu">{b.mime_tur === "application/pdf" ? "PDF" : "Word"}</div>
                  </td>
                  <td><BelgeDurumRozeti durum={b.durum} /></td>
                  <td className="sayi">{b.sayfa_sayisi ?? "–"}</td>
                  <td>
                    {b.uyarili_sayfa_sayisi > 0 ? (
                      <span className="rozet uyari" title="Aslıyla karşılaştırılması gereken sayfa var">
                        ⚠ {b.uyarili_sayfa_sayisi} sayfa kontrol edilmeli
                      </span>
                    ) : b.ocr_sayfa_sayisi > 0 ? (
                      <span className="rozet soluk">{b.ocr_sayfa_sayisi} sayfa OCR</span>
                    ) : <span className="ipucu">–</span>}
                  </td>
                  <td>{tarih(b.yuklenme)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

function BelgeYukle({ davaId, yuklendi }: { davaId: string; yuklendi: () => void }) {
  const oturumHatasi = useOturumHatasi();
  const girdi = useRef<HTMLInputElement>(null);
  const [durum, setDurum] = useState<{ tur: "hata" | "basari"; mesaj: string } | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const [uzerinde, setUzerinde] = useState(false);

  async function gonder(dosyalar: File[]) {
    if (dosyalar.length === 0) return;
    setGonderiliyor(true);
    setDurum(null);
    const hatalar: string[] = [];
    for (const dosya of dosyalar) {
      const form = new FormData();
      form.append("dosya", dosya);
      try {
        await api(`/davalar/${davaId}/belgeler`, { method: "POST", body: form });
      } catch (h) {
        if (oturumHatasi(h)) return;
        hatalar.push(`${dosya.name}: ${h instanceof ApiHatasi ? h.message : "yüklenemedi"}`);
      }
    }
    setGonderiliyor(false);
    if (girdi.current) girdi.current.value = "";
    const basarili = dosyalar.length - hatalar.length;
    setDurum(hatalar.length
      ? { tur: "hata", mesaj: `${basarili} belge yüklendi. Yüklenemeyenler: ${hatalar.join(" · ")}` }
      : { tur: "basari", mesaj: `${basarili} belge yüklendi; metin çıkarma sıraya alındı.` });
    yuklendi();
  }

  function birak(olay: DragEvent) {
    olay.preventDefault();
    setUzerinde(false);
    if (!gonderiliyor) gonder(Array.from(olay.dataTransfer.files));
  }

  return (
    <div className="kart">
      <div
        className={`birakma-alani ${uzerinde ? "uzerinde" : ""}`}
        onDragOver={(o) => { o.preventDefault(); setUzerinde(true); }}
        onDragLeave={() => setUzerinde(false)}
        onDrop={birak}
      >
        <span className="birakma-simgesi"><Simge ad="yukle" boyut={28} /></span>
        <strong>{gonderiliyor ? "Yükleniyor…" : "Belgeleri buraya sürükleyin"}</strong>
        <span className="ipucu">ya da</span>
        <button type="button" className="ikincil" disabled={gonderiliyor} onClick={() => girdi.current?.click()}>
          <Simge ad="yukle" />Bilgisayardan seç
        </button>
        <input ref={girdi} type="file" accept=".pdf,.docx" multiple hidden aria-label="Yüklenecek belgeler"
               onChange={(o) => gonder(Array.from(o.target.files ?? []))} />
        <span className="ipucu">PDF ya da Word (.docx), en fazla 50 MB. Aynı belge aynı dosyaya iki kez yüklenemez.</span>
      </div>
      {durum && <div className={`bildirim ${durum.tur}`}>{durum.mesaj}</div>}
    </div>
  );
}
