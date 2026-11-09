"use client";

// Özet sekmesi: dosyada avukatı bekleyen işler. Her kart ilgili sekmeye ya da belgeye götürür.
// Bekleyen iş yoksa bunu açıkça söyler.

import Link from "next/link";
import { DavaVerisi, Islem } from "./ortak";
import AnalizDenetimi from "./AnalizDenetimi";

export default function OzetSekmesi({ davaId, veri, sekme, islem, mesgul }: {
  davaId: string; veri: DavaVerisi; sekme: (ad: string) => string; islem: Islem; mesgul: boolean;
}) {
  const bulgular = veri.bulgular ?? [];
  const otomatik = bulgular.filter((b) => b.dogrulama_durumu === "otomatik").length;
  const acikCeliski = veri.celiskiler.filter((c) => c.durum === "acik");
  const eksikDelil = veri.harita.flatMap((d) => d.deliller.filter((k) => k.tur === "eksik").map((k) => k.metin));
  const dayanaksiz = veri.harita.reduce((t, d) => t + d.iddialar.filter((i) => i.dayanaksiz).length, 0);
  const ocrBelgeler = (veri.belgeler?.belgeler ?? []).filter((b) => b.uyarili_sayfa_sayisi > 0);
  const islenen = (veri.belgeler?.belgeler ?? []).filter((b) => b.durum === "yuklendi" || b.durum === "isleniyor").length;
  const onayBekleyen = (veri.analiz?.belgeler ?? []).filter((b) => b.ozel_nitelikli && !b.ozel_nitelik_onayli).length;
  const kararVerebilir = veri.analiz?.karar_verebilir ?? false;
  const bekleyen = otomatik + acikCeliski.length + eksikDelil.length + ocrBelgeler.length + onayBekleyen;

  return (
    <>
      <h2 style={{ marginBottom: 10 }}>Bu dosyada sizi bekleyenler</h2>
      {bekleyen === 0 ? (
        <div className="bildirim basari">
          Bekleyen iş yok. {bulgular.length ? "Tüm bulgular incelendi ve açık çelişki yok." : ""}
          {islenen > 0 && ` ${islenen} belge hâlâ işleniyor.`}
        </div>
      ) : (
        <div className="is-izgara">
          {otomatik > 0 && (
            <div className="is-karti">
              <span className="ipucu">İncelenmemiş bulgu</span>
              <span className="ozet-sayi">{otomatik}</span>
              <span className="ipucu">{bulgular.length} bulgudan; onaylanmadan kesin bilgi sayılmaz.</span>
              {kararVerebilir
                ? <Link className="devam" href={sekme("inceleme")}>İncelemeye başla →</Link>
                : <Link className="devam" href={sekme("bulgular")}>Bulguları gör →</Link>}
            </div>
          )}
          {acikCeliski.length > 0 && (
            <div className="is-karti hata">
              <span className="ipucu">Açık çelişki</span>
              <span className="ozet-sayi">{acikCeliski.length}</span>
              <span className="ipucu">{acikCeliski.slice(0, 2).map((c) => c.aciklama.split(":")[0]).join(" · ")}</span>
              <Link className="devam" href={sekme("celiskiler")}>Çelişkilere git →</Link>
            </div>
          )}
          {eksikDelil.length > 0 && (
            <div className="is-karti uyari">
              <span className="ipucu">Dosyada bulunamayan delil</span>
              <span className="ozet-sayi">{eksikDelil.length}</span>
              <span className="ipucu">{eksikDelil.slice(0, 3).join(" · ")}</span>
              <Link className="devam" href={sekme("iddia")}>İddia–delil haritası →</Link>
            </div>
          )}
          {ocrBelgeler.length > 0 && (
            <div className="is-karti uyari">
              <span className="ipucu">Aslıyla karşılaştırılacak OCR sayfası</span>
              <span className="ozet-sayi">{ocrBelgeler.reduce((t, b) => t + b.uyarili_sayfa_sayisi, 0)}</span>
              {ocrBelgeler.slice(0, 3).map((b) => (
                <Link key={b.id} href={`/belgeler/${b.id}`} className="ipucu">{b.orijinal_ad}</Link>
              ))}
            </div>
          )}
          {onayBekleyen > 0 && (
            <div className="is-karti uyari">
              <span className="ipucu">Özel nitelikli veri onayı bekleyen belge</span>
              <span className="ozet-sayi">{onayBekleyen}</span>
              <span className="ipucu">Onay verilmeden analiz edilmez (aşağıda).</span>
            </div>
          )}
        </div>
      )}
      {dayanaksiz > 0 && (
        <p className="ipucu" style={{ marginTop: 10 }}>
          Ayrıca dilekçede {dayanaksiz} iddianın dosyada bağlantılı belgesi bulunamadı —{" "}
          <Link href={sekme("iddia")}>iddia–delil haritası</Link>.
        </p>
      )}
      <div className="bosluk" />
      {veri.analiz && <AnalizDenetimi davaId={davaId} analiz={veri.analiz} islem={islem} mesgul={mesgul} />}
    </>
  );
}
