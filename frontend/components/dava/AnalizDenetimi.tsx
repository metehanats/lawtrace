"use client";

// Analizi başlatma, özel nitelikli belge onayı ve başarısız analizler. Bulgular "otomatik" gelir;
// avukat onaylayana kadar kesin bilgi gibi gösterilmez.

import Link from "next/link";
import { Simge } from "@/components/Simgeler";
import { AnalizBaslatma, AnalizDurumu, gonder, tarih } from "@/lib/api";
import type { Islem } from "./ortak";

export default function AnalizDenetimi({ davaId, analiz, islem, mesgul }: {
  davaId: string; analiz: AnalizDurumu; islem: Islem; mesgul: boolean;
}) {
  const calisan = analiz.belgeler.filter((b) => b.analiz_durumu === "calisiyor").length;
  const onayBekleyen = analiz.belgeler.filter((b) => b.ozel_nitelikli && !b.ozel_nitelik_onayli);
  const hatali = analiz.belgeler.filter((b) => b.analiz_durumu === "hata");
  const sonAnaliz = analiz.belgeler.map((b) => b.analiz_bitis).filter(Boolean).sort().at(-1);

  function analizEt() {
    islem(
      () => gonder<AnalizBaslatma>("POST", `/davalar/${davaId}/analiz`, {}),
      (s) => {
        const parcalar = [`${s.baslatilan.length} belge analiz sırasına alındı.`];
        if (s.onay_bekleyen.length) parcalar.push(`${s.onay_bekleyen.length} belge özel nitelikli veri onayı bekliyor.`);
        if (s.atlanan.length) parcalar.push(`${s.atlanan.length} belge atlandı (${s.atlanan.map((a) => a.neden).join(", ")}).`);
        return parcalar.join(" ");
      },
    );
  }

  return (
    <div className="kart">
      <div className="baslik-satiri" style={{ marginBottom: 6 }}>
        <div>
          <h2 style={{ margin: 0 }}>Analiz</h2>
          <p className="ipucu" style={{ margin: 0 }}>
            {analiz.analiz_acik
              ? `Tarih, tutar, kişi ve kurumlar kaynak sayfa ve alıntısıyla çıkarılır (yerel model: ${analiz.model?.replace(/^ollama:/, "")}).`
              : "Analiz bu büro için kapalı. Büro yöneticisi Yönetim sayfasından açabilir."}
            {sonAnaliz && <> Son analiz: {tarih(sonAnaliz)}.</>}
          </p>
        </div>
        {analiz.analiz_acik && analiz.karar_verebilir && (
          <button onClick={analizEt} disabled={mesgul || calisan > 0}>
            <Simge ad="analiz" />{calisan > 0 ? `Analiz sürüyor (${calisan} belge)…` : "Belgeleri analiz et"}
          </button>
        )}
      </div>

      {onayBekleyen.length > 0 && (
        <div className="bildirim uyari">
          <strong>Özel nitelikli veri içerebilecek belgeler.</strong> Bu belgeler avukat onayı olmadan analiz edilmez.
          <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
            {onayBekleyen.map((b) => (
              <li key={b.belge_id} style={{ marginBottom: 6 }}>
                <Link href={`/belgeler/${b.belge_id}`}>{b.orijinal_ad}</Link>
                <span className="ipucu"> — {b.ozel_nitelik_nedeni}</span>
                {analiz.karar_verebilir && (
                  <button className="ikincil kucuk" style={{ marginLeft: 8 }} disabled={mesgul}
                          onClick={() => islem(() => gonder("POST", `/belgeler/${b.belge_id}/ozel-nitelik-onayi`),
                                               () => `${b.orijinal_ad} analizi için onay verildi.`)}>
                    Analizine onay ver
                  </button>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {hatali.length > 0 && (
        <div className="bildirim hata">
          Analizi başarısız olan belgeler: {hatali.map((b) => `${b.orijinal_ad} (${b.analiz_hatasi ?? "bilinmeyen hata"})`).join(" · ")}
        </div>
      )}
    </div>
  );
}
