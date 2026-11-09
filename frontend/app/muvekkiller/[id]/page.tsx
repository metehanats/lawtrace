"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import { api, DAVA_DURUMU, MUVEKKIL_TURU, MuvekkilAyrintisi, olusturabilir, tarih } from "@/lib/api";

export default function MuvekkilSayfasi() {
  const { id } = useParams<{ id: string }>();
  const kullanici = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [muvekkil, setMuvekkil] = useState<MuvekkilAyrintisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    api<MuvekkilAyrintisi>(`/muvekkiller/${id}`)
      .then(setMuvekkil)
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [id, oturumHatasi]);

  if (hata) return <div className="bildirim hata">{hata}</div>;
  if (!muvekkil) return <p className="ipucu">Yükleniyor…</p>;
  const { iletisim } = muvekkil;

  return (
    <>
      <div className="ekmek">
        <Link href="/muvekkiller">Müvekkiller</Link> / {muvekkil.ad_unvan}
      </div>
      <div className="baslik-satiri">
        <div>
          <h1>{muvekkil.ad_unvan}</h1>
          <p className="alt-baslik">{MUVEKKIL_TURU[muvekkil.tur]} · Kayıt: {tarih(muvekkil.olusturma)}</p>
        </div>
        {olusturabilir(kullanici) && (
          <div className="form-dugmeler" style={{ marginTop: 0 }}>
            <Link className="dugme ikincil" href={`/muvekkiller/${muvekkil.id}/duzenle`}>Düzenle</Link>
            <Link className="dugme" href={`/davalar/yeni?muvekkil=${muvekkil.id}`}>
              Bu müvekkil için dava dosyası aç
            </Link>
          </div>
        )}
      </div>

      <div className="kart">
        <h2>Bilgiler</h2>
        {/* Bu sayfanın görüntülenmesi denetim kaydına yazılır */}
        <dl className="tanim">
          <dt>{muvekkil.tur === "gercek_kisi" ? "T.C. kimlik no" : "Vergi kimlik no"}</dt>
          <dd>{muvekkil.kimlik_no ?? <span className="ipucu">–</span>}</dd>
          <dt>Telefon</dt>
          <dd>{iletisim.telefon ?? <span className="ipucu">–</span>}</dd>
          <dt>E-posta</dt>
          <dd>{iletisim.e_posta ?? <span className="ipucu">–</span>}</dd>
          <dt>Adres</dt>
          <dd style={{ whiteSpace: "pre-wrap" }}>{iletisim.adres ?? <span className="ipucu">–</span>}</dd>
        </dl>
      </div>
      <div className="bosluk" />
      <div className="kart tablo-kap">
        <h2>Dava dosyaları</h2>
        {muvekkil.davalar.length === 0 ? (
          <p className="ipucu">Erişebildiğiniz bir dava dosyası yok.</p>
        ) : (
          <table>
            <thead>
              <tr><th>Dosya no</th><th>Başlık</th><th>Durum</th></tr>
            </thead>
            <tbody>
              {muvekkil.davalar.map((d) => (
                <tr key={d.id}>
                  <td><Link href={`/davalar/${d.id}`}>{d.dosya_no}</Link></td>
                  <td>{d.baslik}</td>
                  <td><span className="rozet soluk">{DAVA_DURUMU[d.durum]}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
