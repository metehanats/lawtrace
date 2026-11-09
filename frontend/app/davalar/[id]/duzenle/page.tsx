"use client";

// Dava dosyası bilgilerini ve durumunu düzenleme. Kapalı dosyada yalnızca durum değiştirilebilir
// (yeniden açma); diğer alanlar dosya açılınca düzenlenir.

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";
import { useOturumHatasi } from "@/components/Korumali";
import { api, ApiHatasi, Dava, DAVA_DURUMU, gonder, MuvekkilOzeti } from "@/lib/api";

const DURUM_ACIKLAMASI: Record<Dava["durum"], string> = {
  acik: "Dosya üzerinde çalışılıyor.",
  beklemede: "Çalışma ara verildi; tüm işlemler açık kalır.",
  kapali: "Salt okunur: belge yükleme, analiz, bulgu ve çelişki kararları kapanır. Yeniden açılabilir.",
};

export default function DavaDuzenleSayfasi() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const oturumHatasi = useOturumHatasi();
  const [dava, setDava] = useState<Dava | null>(null);
  const [muvekkiller, setMuvekkiller] = useState<MuvekkilOzeti[] | null>(null);
  const [alanlar, setAlanlar] = useState({ muvekkil_id: "", dosya_no: "", baslik: "", dava_turu: "" });
  const [durum, setDurum] = useState<Dava["durum"]>("acik");
  const [hata, setHata] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  useEffect(() => {
    Promise.all([api<Dava>(`/davalar/${id}`), api<{ muvekkiller: MuvekkilOzeti[] }>("/muvekkiller")])
      .then(([d, m]) => {
        setDava(d);
        setMuvekkiller(m.muvekkiller);
        setAlanlar({ muvekkil_id: d.muvekkil_id, dosya_no: d.dosya_no, baslik: d.baslik, dava_turu: d.dava_turu ?? "" });
        setDurum(d.durum);
      })
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [id, oturumHatasi]);

  if (hata && !dava) return <div className="bildirim hata">{hata}</div>;
  if (!dava || !muvekkiller) return <p className="ipucu">Yükleniyor…</p>;
  if (!dava.duzenleyebilir) {
    return <div className="bildirim hata">Dosyayı yalnızca sorumlusu ya da büro yöneticisi düzenleyebilir.</div>;
  }
  // Kapalı dosyada bilgiler kilitli; durum "kapalı"dan çıkarılınca açılır
  const kilitli = dava.durum === "kapali" && durum === "kapali";

  const degistir = (ad: keyof typeof alanlar) => (o: { target: { value: string } }) =>
    setAlanlar((a) => ({ ...a, [ad]: o.target.value }));

  async function kaydet(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    setGonderiliyor(true);
    try {
      await gonder<void>("PUT", `/davalar/${id}`, { ...alanlar, dava_turu: alanlar.dava_turu.trim() || null, durum });
      router.push(`/davalar/${id}`);
    } catch (h) {
      if (!oturumHatasi(h)) setHata(h instanceof ApiHatasi ? h.message : "Kaydedilemedi.");
      setGonderiliyor(false);
    }
  }

  return (
    <>
      <div className="ekmek">
        <Link href="/davalar">Dava dosyaları</Link> / <Link href={`/davalar/${id}`}>{dava.dosya_no}</Link> / Düzenle
      </div>
      <h1 style={{ marginBottom: 16 }}>Dava dosyasını düzenle</h1>
      <form className="kart form-kart" onSubmit={kaydet}>
        {hata && <div className="bildirim hata" role="alert">{hata}</div>}
        <label>Durum</label>
        <div className="secenekler" role="radiogroup">
          {(["acik", "beklemede", "kapali"] as const).map((d) => (
            <label key={d}>
              <input type="radio" name="durum" checked={durum === d} onChange={() => setDurum(d)} />
              {DAVA_DURUMU[d]}
            </label>
          ))}
        </div>
        <p className="ipucu">{DURUM_ACIKLAMASI[durum]}</p>

        <fieldset disabled={kilitli} style={{ border: 0, padding: 0, margin: 0 }}>
          <label htmlFor="muvekkil">Müvekkil</label>
          <select id="muvekkil" required value={alanlar.muvekkil_id} onChange={degistir("muvekkil_id")}>
            {muvekkiller.map((m) => (
              <option key={m.id} value={m.id}>
                {m.ad_unvan}{m.kimlik_no_maskeli ? ` (${m.kimlik_no_maskeli})` : ""}
              </option>
            ))}
          </select>
          <div className="form-izgara">
            <div>
              <label htmlFor="dosya_no">Dosya no</label>
              <input id="dosya_no" type="text" required maxLength={60} value={alanlar.dosya_no}
                     onChange={degistir("dosya_no")} />
            </div>
            <div>
              <label htmlFor="dava_turu">Dava türü</label>
              <input id="dava_turu" type="text" maxLength={100} value={alanlar.dava_turu} onChange={degistir("dava_turu")} />
            </div>
            <div className="tam">
              <label htmlFor="baslik">Başlık</label>
              <input id="baslik" type="text" required maxLength={300} value={alanlar.baslik} onChange={degistir("baslik")} />
            </div>
          </div>
        </fieldset>
        <p className="ipucu">
          {kilitli ? "Dosya kapalı: bilgileri değiştirmek için önce durumu Açık ya da Beklemede yapın. "
            : ""}
          Değişiklikler eski ve yeni değerleriyle denetim kaydına yazılır.
        </p>
        <div className="form-dugmeler">
          <button type="submit" disabled={gonderiliyor}>{gonderiliyor ? "Kaydediliyor…" : "Kaydet"}</button>
          <Link className="dugme ikincil" href={`/davalar/${id}`}>Vazgeç</Link>
        </div>
      </form>
    </>
  );
}
