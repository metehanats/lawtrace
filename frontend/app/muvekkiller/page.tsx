"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import { api, MUVEKKIL_TURU, MuvekkilOzeti, olusturabilir } from "@/lib/api";

export default function MuvekkillerSayfasi() {
  const kullanici = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [muvekkiller, setMuvekkiller] = useState<MuvekkilOzeti[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [arama, setArama] = useState("");

  useEffect(() => {
    api<{ muvekkiller: MuvekkilOzeti[] }>("/muvekkiller")
      .then((v) => setMuvekkiller(v.muvekkiller))
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [oturumHatasi]);

  const aranan = arama.trim().toLocaleLowerCase("tr");
  const gorunen = muvekkiller?.filter((m) => !aranan || m.ad_unvan.toLocaleLowerCase("tr").includes(aranan));

  return (
    <>
      <div className="baslik-satiri">
        <div>
          <h1>Müvekkiller</h1>
          <p className="alt-baslik">
            {olusturabilir(kullanici)
              ? "Bürodaki tüm müvekkiller (çıkar çatışması kontrolü için)"
              : "Erişiminiz olan dosyaların müvekkilleri"}
          </p>
        </div>
        {olusturabilir(kullanici) && (
          <Link className="dugme" href="/muvekkiller/yeni">
            Yeni müvekkil
          </Link>
        )}
      </div>
      {hata && <div className="bildirim hata">{hata}</div>}
      <div className="kart tablo-kap">
        <div style={{ maxWidth: 320, marginBottom: 12 }}>
          <input type="text" placeholder="Ada göre ara" aria-label="Müvekkil ara" value={arama}
                 onChange={(o) => setArama(o.target.value)} />
        </div>
        {gorunen === undefined ? (
          <p className="ipucu">Yükleniyor…</p>
        ) : gorunen.length === 0 ? (
          <p className="ipucu">{muvekkiller?.length ? "Aramayla eşleşen müvekkil yok." : "Henüz müvekkil yok."}</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Ad / unvan</th>
                <th>Tür</th>
                <th>Kimlik / vergi no</th>
                <th className="sayi">Dosya</th>
              </tr>
            </thead>
            <tbody>
              {gorunen.map((m) => (
                <tr key={m.id}>
                  <td>
                    <Link href={`/muvekkiller/${m.id}`}>{m.ad_unvan}</Link>
                  </td>
                  <td>{MUVEKKIL_TURU[m.tur]}</td>
                  <td className="ipucu">{m.kimlik_no_maskeli ?? "–"}</td>
                  <td className="sayi">{m.dava_sayisi}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
