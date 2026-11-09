"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, Suspense, useEffect, useState } from "react";
import { useOturumHatasi } from "@/components/Korumali";
import { api, ApiHatasi, gonder, MuvekkilOzeti } from "@/lib/api";

function YeniDavaFormu() {
  const router = useRouter();
  const parametreler = useSearchParams();
  const oturumHatasi = useOturumHatasi();
  const [muvekkiller, setMuvekkiller] = useState<MuvekkilOzeti[] | null>(null);
  const [muvekkilId, setMuvekkilId] = useState(parametreler.get("muvekkil") ?? "");
  const [dosyaNo, setDosyaNo] = useState("");
  const [baslik, setBaslik] = useState("");
  const [davaTuru, setDavaTuru] = useState("");
  const [hata, setHata] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);

  useEffect(() => {
    api<{ muvekkiller: MuvekkilOzeti[] }>("/muvekkiller")
      .then((v) => setMuvekkiller(v.muvekkiller))
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [oturumHatasi]);

  async function kaydet(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    setGonderiliyor(true);
    try {
      const { id } = await gonder<{ id: string }>("POST", "/davalar", {
        muvekkil_id: muvekkilId,
        dosya_no: dosyaNo,
        baslik,
        dava_turu: davaTuru.trim() || null,
      });
      router.push(`/davalar/${id}`);
    } catch (h) {
      if (!oturumHatasi(h)) setHata(h instanceof ApiHatasi ? h.message : "Kaydedilemedi.");
      setGonderiliyor(false);
    }
  }

  return (
    <>
      <div className="ekmek">
        <Link href="/davalar">Dava dosyaları</Link> / Yeni
      </div>
      <h1 style={{ marginBottom: 16 }}>Yeni dava dosyası</h1>
      <form className="kart form-kart" onSubmit={kaydet}>
        {hata && <div className="bildirim hata" role="alert">{hata}</div>}
        <label htmlFor="muvekkil">Müvekkil</label>
        <select id="muvekkil" required value={muvekkilId} onChange={(o) => setMuvekkilId(o.target.value)}
                disabled={muvekkiller === null}>
          <option value="">{muvekkiller === null ? "Yükleniyor…" : "Müvekkil seçin"}</option>
          {muvekkiller?.map((m) => (
            <option key={m.id} value={m.id}>
              {m.ad_unvan}{m.kimlik_no_maskeli ? ` (${m.kimlik_no_maskeli})` : ""}
            </option>
          ))}
        </select>
        <p className="ipucu">
          Listede yok mu? <Link href="/muvekkiller/yeni?donus=yeni-dava">Yeni müvekkil ekleyin</Link>.
        </p>
        <div className="form-izgara">
          <div>
            <label htmlFor="dosya_no">Dosya no</label>
            <input id="dosya_no" type="text" required maxLength={60} placeholder="ör. 2026/145" value={dosyaNo}
                   onChange={(o) => setDosyaNo(o.target.value)} />
          </div>
          <div>
            <label htmlFor="dava_turu">Dava türü</label>
            <input id="dava_turu" type="text" maxLength={100} placeholder="ör. Alacak" value={davaTuru}
                   onChange={(o) => setDavaTuru(o.target.value)} />
          </div>
          <div className="tam">
            <label htmlFor="baslik">Başlık</label>
            <input id="baslik" type="text" required maxLength={300} value={baslik}
                   onChange={(o) => setBaslik(o.target.value)} />
          </div>
        </div>
        <p className="ipucu">Dosyayı açan kişi dosyanın sorumlusu olur; diğer kişilere erişimi dosya ekranından verebilirsiniz.</p>
        <div className="form-dugmeler">
          <button type="submit" disabled={gonderiliyor}>{gonderiliyor ? "Kaydediliyor…" : "Dosyayı aç"}</button>
          <Link className="dugme ikincil" href="/davalar">Vazgeç</Link>
        </div>
      </form>
    </>
  );
}

export default function YeniDavaSayfasi() {
  return (
    <Suspense>
      <YeniDavaFormu />
    </Suspense>
  );
}
