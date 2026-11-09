"use client";

import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { BelgeDurumRozeti, GuvenRozeti } from "@/components/Durum";
import { useOturumHatasi } from "@/components/Korumali";
import VurguluMetin from "@/components/VurguluMetin";
import { api, BelgeAyrintisi, Dava, Sayfa, tarih } from "@/lib/api";

const GOREV_ADI: Record<string, string> = { metin_cikarma: "Metin çıkarma", ocr: "OCR", bolme: "Bölme", analiz: "Analiz" };
const GOREV_DURUMU: Record<string, string> = { bekliyor: "Bekliyor", calisiyor: "Çalışıyor", tamam: "Tamam", hata: "Hata" };

export default function BelgeSayfasi() {
  return (
    <Suspense fallback={<p className="ipucu">Yükleniyor…</p>}>
      <BelgeGorunumu />
    </Suspense>
  );
}

function BelgeGorunumu() {
  const { id } = useParams<{ id: string }>();
  const parametreler = useSearchParams();
  const hedefSayfa = Number(parametreler.get("sayfa")) || null;
  const vurguBas = parametreler.has("bas") ? Number(parametreler.get("bas")) : null;
  const vurguBit = parametreler.has("bit") ? Number(parametreler.get("bit")) : null;
  const oturumHatasi = useOturumHatasi();
  const [belge, setBelge] = useState<BelgeAyrintisi | null>(null);
  const [dava, setDava] = useState<Dava | null>(null);
  const [seciliNo, setSeciliNo] = useState<number | null>(null);
  const [sayfa, setSayfa] = useState<Sayfa | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    api<BelgeAyrintisi>(`/belgeler/${id}`)
      .then((b) => {
        setBelge(b);
        const ilk = b.sayfalar.find((s) => s.sayfa_no === hedefSayfa) ?? b.sayfalar[0];
        if (ilk) setSeciliNo(ilk.sayfa_no);
        return api<Dava>(`/davalar/${b.dava_dosyasi_id}`).then(setDava);
      })
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
    // Hedef sayfa yalnızca ilk açılışta uygulanır; bağımlılıklara bilerek eklenmedi
  }, [id, oturumHatasi]);

  useEffect(() => {
    if (seciliNo === null) return;
    setSayfa(null);
    api<Sayfa>(`/belgeler/${id}/sayfalar/${seciliNo}`)
      .then(setSayfa)
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [id, seciliNo, oturumHatasi]);

  if (hata && !belge) return <div className="bildirim hata">{hata}</div>;
  if (!belge) return <p className="ipucu">Yükleniyor…</p>;

  const uyariliSayfa = belge.sayfalar.filter((s) => s.asliyla_karsilastir).length;

  return (
    <>
      <div className="ekmek">
        <Link href="/davalar">Dava dosyaları</Link> /{" "}
        {dava ? <Link href={`/davalar/${dava.id}`}>{dava.dosya_no}</Link> : "…"} / Belge
      </div>
      <div className="baslik-satiri">
        <div>
          <h1>{belge.orijinal_ad}</h1>
          <p className="alt-baslik">
            <BelgeDurumRozeti durum={belge.durum} /> · {belge.sayfa_sayisi ?? "–"} sayfa · Yüklenme:{" "}
            {tarih(belge.yuklenme)}
          </p>
        </div>
        <div className="sag">
          {/* İndirme denetim kaydına "dışa aktarım" olarak yazılır */}
          <a className="dugme ikincil" href={`/api/belgeler/${belge.id}/dosya`}>
            Orijinal dosyayı indir
          </a>
        </div>
      </div>

      {uyariliSayfa > 0 && (
        <div className="bildirim uyari">
          Bu belgede {uyariliSayfa} sayfa taranmış görüntüden düşük güvenle okundu. Bu sayfalardaki tarih, tutar ve
          isimleri belgenin aslıyla karşılaştırın.
        </div>
      )}
      {belge.gorevler.some((g) => g.durum === "hata") && (
        <div className="bildirim hata">
          {belge.gorevler
            .filter((g) => g.durum === "hata")
            .map((g) => `${GOREV_ADI[g.adim] ?? g.adim} başarısız oldu: ${g.hata_mesaji ?? "bilinmeyen hata"}`)
            .join(" · ")}
        </div>
      )}

      {belge.sayfalar.length === 0 ? (
        <div className="kart">
          <p className="ipucu">
            {belge.durum === "hata"
              ? "Bu belgeden metin çıkarılamadı."
              : "Belge henüz işleniyor; sayfalar hazır olunca burada görünecek."}
          </p>
          <GorevListesi belge={belge} />
        </div>
      ) : (
        <div className="izgara">
          <aside className="kart">
            <h2>Sayfalar</h2>
            <ul className="sayfa-listesi">
              {belge.sayfalar.map((s) => (
                <li key={s.sayfa_no}>
                  <button aria-current={s.sayfa_no === seciliNo} onClick={() => setSeciliNo(s.sayfa_no)}>
                    <span>Sayfa {s.sayfa_no}</span>
                    {s.metin_kaynagi === "ocr" && (
                      <GuvenRozeti guven={s.ocr_guven_skoru} uyari={s.asliyla_karsilastir} />
                    )}
                  </button>
                </li>
              ))}
            </ul>
            <GorevListesi belge={belge} />
          </aside>
          <section className="kart">
            {sayfa === null ? (
              <p className="ipucu">Sayfa yükleniyor…</p>
            ) : (
              <>
                <div className="baslik-satiri" style={{ marginBottom: 10 }}>
                  <h2 style={{ margin: 0 }}>Sayfa {sayfa.sayfa_no}</h2>
                  <span className="ipucu">
                    {sayfa.metin_kaynagi === "ocr" ? "Taranmış görüntüden OCR ile okundu" : "Belgedeki metin"}
                  </span>
                </div>
                {sayfa.uyari && <div className="bildirim uyari">⚠ {sayfa.uyari}</div>}
                {sayfa.sayfa_no === hedefSayfa && vurguBas !== null && (
                  <p className="ipucu" style={{ marginTop: 0 }}>Sarı ile işaretli bölüm, bulgunun kaynak alıntısıdır.</p>
                )}
                <div className="metin-alani">
                  {sayfa.metin ? (
                    <VurguluMetin metin={sayfa.metin}
                                  bas={sayfa.sayfa_no === hedefSayfa ? vurguBas : null}
                                  bit={sayfa.sayfa_no === hedefSayfa ? vurguBit : null} />
                  ) : (
                    <span className="ipucu">(Bu sayfada metin yok.)</span>
                  )}
                </div>
              </>
            )}
          </section>
        </div>
      )}
    </>
  );
}

function GorevListesi({ belge }: { belge: BelgeAyrintisi }) {
  if (!belge.gorevler.length) return null;
  return (
    <div style={{ marginTop: 16 }}>
      <div className="ipucu" style={{ fontWeight: 600, marginBottom: 4 }}>
        İşleme adımları
      </div>
      {belge.gorevler.map((g, i) => (
        <div key={i} className="ipucu">
          {GOREV_ADI[g.adim] ?? g.adim}: {GOREV_DURUMU[g.durum] ?? g.durum}
          {g.tekrar_sayisi > 0 ? ` (${g.tekrar_sayisi} deneme)` : ""}
        </div>
      ))}
    </div>
  );
}
