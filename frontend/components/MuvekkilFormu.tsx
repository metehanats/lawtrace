"use client";

// Yeni müvekkil ve müvekkil düzenleme sayfalarının ortak formu.

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useOturumHatasi } from "@/components/Korumali";
import { ApiHatasi, MuvekkilTuru } from "@/lib/api";

export type MuvekkilAlanlari = {
  tur: MuvekkilTuru;
  ad_unvan: string;
  kimlik_no: string;
  telefon: string;
  e_posta: string;
  adres: string;
};

export const BOS_MUVEKKIL: MuvekkilAlanlari = {
  tur: "gercek_kisi", ad_unvan: "", kimlik_no: "", telefon: "", e_posta: "", adres: "",
};

/** API'ye gidecek gövde: boş alanlar null olur (düzenlemede boş bırakılan alan silinir). */
export function muvekkilGovdesi(a: MuvekkilAlanlari) {
  const bos = (v: string) => v.trim() || null;
  return {
    tur: a.tur,
    ad_unvan: a.ad_unvan,
    kimlik_no: bos(a.kimlik_no),
    telefon: bos(a.telefon),
    e_posta: bos(a.e_posta),
    adres: bos(a.adres),
  };
}

export default function MuvekkilFormu({
  baslangic, kaydet, vazgec, ipucu,
}: {
  baslangic: MuvekkilAlanlari;
  kaydet: (alanlar: MuvekkilAlanlari) => Promise<void>;
  vazgec: string;
  ipucu?: React.ReactNode;
}) {
  const oturumHatasi = useOturumHatasi();
  const [alanlar, setAlanlar] = useState(baslangic);
  const [hata, setHata] = useState<string | null>(null);
  const [gonderiliyor, setGonderiliyor] = useState(false);
  const { tur } = alanlar;

  const degistir = (ad: keyof MuvekkilAlanlari) => (o: { target: { value: string } }) =>
    setAlanlar((a) => ({ ...a, [ad]: o.target.value }));

  async function gonder(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    setGonderiliyor(true);
    try {
      await kaydet(alanlar);
    } catch (h) {
      if (!oturumHatasi(h)) setHata(h instanceof ApiHatasi ? h.message : "Kaydedilemedi.");
      setGonderiliyor(false);
    }
  }

  return (
    <form className="kart form-kart" onSubmit={gonder}>
      {hata && <div className="bildirim hata" role="alert">{hata}</div>}
      <label>Tür</label>
      <div className="secenekler" role="radiogroup">
        {(["gercek_kisi", "tuzel_kisi"] as const).map((t) => (
          <label key={t}>
            <input type="radio" name="tur" checked={tur === t} onChange={() => setAlanlar((a) => ({ ...a, tur: t }))} />
            {t === "gercek_kisi" ? "Gerçek kişi" : "Tüzel kişi"}
          </label>
        ))}
      </div>
      <div className="form-izgara">
        <div className="tam">
          <label htmlFor="ad_unvan">{tur === "gercek_kisi" ? "Ad soyad" : "Unvan"}</label>
          <input id="ad_unvan" type="text" required maxLength={300} value={alanlar.ad_unvan}
                 onChange={degistir("ad_unvan")} />
        </div>
        <div>
          <label htmlFor="kimlik_no">{tur === "gercek_kisi" ? "T.C. kimlik no" : "Vergi kimlik no"}</label>
          <input id="kimlik_no" type="text" inputMode="numeric" autoComplete="off"
                 maxLength={tur === "gercek_kisi" ? 11 : 10} value={alanlar.kimlik_no}
                 onChange={degistir("kimlik_no")} />
        </div>
        <div>
          <label htmlFor="telefon">Telefon</label>
          <input id="telefon" type="text" autoComplete="off" value={alanlar.telefon} onChange={degistir("telefon")} />
        </div>
        <div className="tam">
          <label htmlFor="e_posta">E-posta</label>
          <input id="e_posta" type="email" autoComplete="off" value={alanlar.e_posta} onChange={degistir("e_posta")} />
        </div>
        <div className="tam">
          <label htmlFor="adres">Adres</label>
          <textarea id="adres" maxLength={500} value={alanlar.adres} onChange={degistir("adres")} />
        </div>
      </div>
      <p className="ipucu">
        Kimlik numarası ve iletişim bilgileri şifrelenerek saklanır. Listede kimlik numarasının yalnızca son iki
        hanesi görünür.{ipucu && <> {ipucu}</>}
      </p>
      <div className="form-dugmeler">
        <button type="submit" disabled={gonderiliyor}>{gonderiliyor ? "Kaydediliyor…" : "Kaydet"}</button>
        <Link className="dugme ikincil" href={vazgec}>Vazgeç</Link>
      </div>
    </form>
  );
}
