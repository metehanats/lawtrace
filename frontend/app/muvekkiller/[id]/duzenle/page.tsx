"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import MuvekkilFormu, { MuvekkilAlanlari, muvekkilGovdesi } from "@/components/MuvekkilFormu";
import { api, gonder, MuvekkilAyrintisi, olusturabilir } from "@/lib/api";

export default function MuvekkilDuzenleSayfasi() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const kullanici = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [muvekkil, setMuvekkil] = useState<MuvekkilAyrintisi | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  useEffect(() => {
    api<MuvekkilAyrintisi>(`/muvekkiller/${id}`)
      .then(setMuvekkil)
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [id, oturumHatasi]);

  if (!olusturabilir(kullanici)) return <div className="bildirim hata">Müvekkil bilgilerini düzenleme yetkiniz yok.</div>;
  if (hata) return <div className="bildirim hata">{hata}</div>;
  if (!muvekkil) return <p className="ipucu">Yükleniyor…</p>;

  const { iletisim } = muvekkil;
  const baslangic: MuvekkilAlanlari = {
    tur: muvekkil.tur,
    ad_unvan: muvekkil.ad_unvan,
    kimlik_no: muvekkil.kimlik_no ?? "",
    telefon: iletisim.telefon ?? "",
    e_posta: iletisim.e_posta ?? "",
    adres: iletisim.adres ?? "",
  };

  async function kaydet(alanlar: MuvekkilAlanlari) {
    await gonder<void>("PUT", `/muvekkiller/${id}`, muvekkilGovdesi(alanlar));
    router.push(`/muvekkiller/${id}`);
  }

  return (
    <>
      <div className="ekmek">
        <Link href="/muvekkiller">Müvekkiller</Link> / <Link href={`/muvekkiller/${id}`}>{muvekkil.ad_unvan}</Link> / Düzenle
      </div>
      <h1 style={{ marginBottom: 16 }}>Müvekkil bilgilerini düzenle</h1>
      <MuvekkilFormu
        baslangic={baslangic}
        kaydet={kaydet}
        vazgec={`/muvekkiller/${id}`}
        ipucu="Boş bırakılan alan silinir. Düzenleme denetim kaydına yazılır (yalnızca değişen alanların adı)."
      />
    </>
  );
}
