"use client";

// Dava çalışma alanı: sekmeler (Özet, Belgeler, Bulgular, Çelişkiler, Zaman çizelgesi, İddia–delil,
// Erişim) ve bulguları kaynağıyla inceleme ekranı. Seçili sekme adreste durur (?sekme=), böylece geri
// tuşu ve paylaşılan bağlantı aynı yere döner. Veri bir kez yüklenir, tüm sekmeler onu paylaşır.

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useLayoutEffect, useRef, useState } from "react";
import { Simge, SimgeAdi } from "@/components/Simgeler";
import ErisimYonetimi from "@/components/ErisimYonetimi";
import IddiaHaritasi from "@/components/IddiaHaritasi";
import ZamanCizelgesi from "@/components/ZamanCizelgesi";
import AnalizDenetimi from "@/components/dava/AnalizDenetimi";
import BelgelerSekmesi from "@/components/dava/BelgelerSekmesi";
import BulguTablolari from "@/components/dava/BulguTablolari";
import CeliskiListesi from "@/components/dava/CeliskiListesi";
import IncelemeEkrani from "@/components/dava/IncelemeEkrani";
import OzetSekmesi from "@/components/dava/OzetSekmesi";
import { useDavaVerisi, useIslem } from "@/components/dava/ortak";
import { DAVA_DURUMU } from "@/lib/api";

export default function DavaSayfasi() {
  return (
    <Suspense fallback={<p className="ipucu">Yükleniyor…</p>}>
      <DavaCalismaAlani />
    </Suspense>
  );
}

function DavaCalismaAlani() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const sekme = useSearchParams().get("sekme") ?? "ozet";
  const veri = useDavaVerisi(id);
  const { islem, mesgul, bildirim } = useIslem(veri.yukle);
  const adres = (ad: string) => (ad === "ozet" ? `/davalar/${id}` : `/davalar/${id}?sekme=${ad}`);

  if (veri.hata && !veri.dava) return <div className="bildirim hata">{veri.hata}</div>;
  if (!veri.dava || !veri.belgeler || !veri.analiz || !veri.bulgular) return <p className="ipucu">Yükleniyor…</p>;
  const { dava, belgeler, analiz, bulgular } = veri;
  const kapali = dava.durum === "kapali";

  const otomatik = bulgular.filter((b) => b.dogrulama_durumu === "otomatik").length;
  const acikCeliski = veri.celiskiler.filter((c) => c.durum === "acik").length;
  const eksikDelil = veri.harita.reduce((t, d) => t + d.deliller.filter((k) => k.tur === "eksik").length, 0);
  const sekmeler: Sekme[] = [
    { ad: "ozet", baslik: "Özet", simge: "ozet" },
    { ad: "belgeler", baslik: "Belgeler", simge: "belgeler", sayi: belgeler.toplam },
    { ad: "bulgular", baslik: "Bulgular", simge: "bulgular", sayi: otomatik || undefined, sinif: "uyari" },
    { ad: "celiskiler", baslik: "Çelişkiler", simge: "celiskiler", sayi: acikCeliski || undefined, sinif: "hata" },
    { ad: "zaman", baslik: "Zaman çizelgesi", simge: "zaman", sayi: veri.olaylar.length || undefined },
    { ad: "iddia", baslik: "İddia–delil", simge: "iddia", sayi: eksikDelil || undefined, sinif: "uyari" },
    { ad: "erisim", baslik: "Erişim", simge: "erisim" },
  ];
  // İnceleme ekranı Bulgular sekmesinin bir görünümüdür
  const etkin = sekme === "inceleme" ? "bulgular" : sekme;

  return (
    <>
      <div className="ekmek">
        <Link href="/davalar">Dava dosyaları</Link> / {dava.dosya_no}
      </div>
      <div className="baslik-satiri" style={{ marginBottom: 8 }}>
        <div>
          <h1>{dava.baslik}</h1>
          <p className="alt-baslik">
            {dava.dosya_no} · Müvekkil: {dava.muvekkil}
            {dava.dava_turu ? ` · ${dava.dava_turu}` : ""} · {DAVA_DURUMU[dava.durum]}
            {veri.surenIs && <> · <span className="rozet">İşleniyor…</span></>}
          </p>
        </div>
        {dava.duzenleyebilir && (
          <Link className="dugme ikincil" href={`/davalar/${id}/duzenle`}>
            {kapali ? "Yeniden aç / düzenle" : "Düzenle"}
          </Link>
        )}
      </div>
      {kapali && (
        <div className="bildirim uyari" role="status">
          Bu dosya kapalı ve salt okunur: belge yüklenemez, analiz başlatılamaz, bulgu ve çelişki kararı verilemez.
          {dava.duzenleyebilir && " Değişiklik için dosyayı yeniden açın."}
        </div>
      )}

      <SekmeCubugu sekmeler={sekmeler} etkin={etkin} adres={adres} />

      {bildirim && <div className={`bildirim ${bildirim.tur}`} role="status">{bildirim.mesaj}</div>}
      {veri.hata && <div className="bildirim hata">{veri.hata}</div>}

      {/* key: sekme değişince içerik yeniden kurulur ve hafifçe belirir */}
      <div key={sekme} className="sekme-icerik">

      {sekme === "ozet" && <OzetSekmesi davaId={id} veri={veri} sekme={adres} islem={islem} mesgul={mesgul} />}
      {sekme === "belgeler" && <BelgelerSekmesi davaId={id} liste={belgeler} yuklendi={veri.yukle} kapali={kapali} />}
      {sekme === "bulgular" && (
        <>
          <AnalizDenetimi davaId={id} analiz={analiz} islem={islem} mesgul={mesgul} />
          <div className="bosluk" />
          <BulguTablolari bulgular={bulgular} celiskiler={veri.celiskiler} kararVerebilir={analiz.karar_verebilir}
                          islem={islem} mesgul={mesgul} incele={() => router.push(adres("inceleme"))} />
        </>
      )}
      {sekme === "inceleme" && (
        <IncelemeEkrani bulgular={bulgular} celiskiler={veri.celiskiler} kararVerebilir={analiz.karar_verebilir}
                        islem={islem} mesgul={mesgul} geri={adres("bulgular")} />
      )}
      {sekme === "celiskiler" && (
        <CeliskiListesi celiskiler={veri.celiskiler} kararVerebilir={analiz.karar_verebilir} islem={islem} mesgul={mesgul} />
      )}
      {sekme === "zaman" && (
        <div className="kart">
          {veri.olaylar.length ? <ZamanCizelgesi olaylar={veri.olaylar} />
            : <p className="ipucu" style={{ margin: 0 }}>Henüz tarih bulunmadı. Belgeler analiz edildiğinde olaylar burada sıralanır.</p>}
        </div>
      )}
      {sekme === "iddia" && (
        <div className="kart">
          {veri.harita.length ? <IddiaHaritasi dilekceler={veri.harita} />
            : <p className="ipucu" style={{ margin: 0 }}>Dosyada bölüm başlıkları (AÇIKLAMALAR, DELİLLER…) olan bir dilekçe bulunamadı.</p>}
        </div>
      )}
      {sekme === "erisim" && <ErisimYonetimi davaId={id} />}
      </div>
    </>
  );
}

type Sekme = { ad: string; baslik: string; simge: SimgeAdi; sayi?: number; sinif?: string };

/** Sekmeler; altındaki çizgi seçilen sekmeye kayar (ölçülerek konumlanır). */
function SekmeCubugu({ sekmeler, etkin, adres }: { sekmeler: Sekme[]; etkin: string; adres: (ad: string) => string }) {
  const cubuk = useRef<HTMLElement>(null);
  const [cizgi, setCizgi] = useState<{ left: number; width: number } | null>(null);

  useLayoutEffect(() => {
    function olc() {
      const a = cubuk.current?.querySelector<HTMLElement>('a[aria-current="page"]');
      if (a) setCizgi({ left: a.offsetLeft, width: a.offsetWidth });
    }
    olc();
    window.addEventListener("resize", olc);
    return () => window.removeEventListener("resize", olc);
  }, [etkin, sekmeler.map((s) => s.sayi).join()]);

  return (
    <nav ref={cubuk} className="sekmeler" aria-label="Dava bölümleri">
      {sekmeler.map((s) => (
        <Link key={s.ad} href={adres(s.ad)} aria-current={s.ad === etkin ? "page" : undefined}>
          <Simge ad={s.simge} />
          {s.baslik}
          {s.sayi !== undefined && <span className={`sekme-sayi ${s.sinif ?? ""}`}>{s.sayi}</span>}
        </Link>
      ))}
      {cizgi && <span className="sekme-cizgisi" style={{ left: cizgi.left, width: cizgi.width }} aria-hidden />}
    </nav>
  );
}
