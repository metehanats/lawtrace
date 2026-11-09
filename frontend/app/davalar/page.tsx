"use client";

// Dava dosyaları listesi: arama, "bekleyen iş" sütunu ve hangi dosyaya önce bakılacağını gösteren sıralama.
// Arama tarayıcıda yapılır (liste büronun kendi dosyaları kadar); Türkçe harf farkı gözetilmez ("ayse" → "Ayşe").

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import { Simge } from "@/components/Simgeler";
import { api, Dava, DAVA_DURUMU, olusturabilir, tarih } from "@/lib/api";

const HARF: Record<string, string> = { ç: "c", ğ: "g", ı: "i", i̇: "i", ö: "o", ş: "s", ü: "u", â: "a", î: "i", û: "u" };
const sadelestir = (s: string) => s.toLocaleLowerCase("tr-TR").replace(/[çğıöşüâîû]|i̇/g, (h) => HARF[h] ?? h);

const bekleyenToplam = (d: Dava) => d.incelenmemis_bulgu + d.acik_celiski + d.kontrol_ocr_sayfa + d.onay_bekleyen_belge;

type Siralama = "guncelleme" | "bekleyen" | "dosya_no";

export default function DavalarSayfasi() {
  const kullanici = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [davalar, setDavalar] = useState<Dava[] | null>(null);
  const [hata, setHata] = useState<string | null>(null);
  const [arama, setArama] = useState("");
  const [yalnizBekleyen, setYalnizBekleyen] = useState(false);
  const [siralama, setSiralama] = useState<Siralama>("guncelleme");
  const aramaKutusu = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api<{ davalar: Dava[] }>("/davalar")
      .then((v) => setDavalar(v.davalar))
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [oturumHatasi]);

  // "/" tuşu aramaya odaklanır (yazı alanındayken değil)
  useEffect(() => {
    function tus(o: KeyboardEvent) {
      const hedef = o.target as HTMLElement;
      if (o.key === "/" && !["INPUT", "TEXTAREA", "SELECT"].includes(hedef.tagName)) {
        o.preventDefault();
        aramaKutusu.current?.focus();
      }
    }
    window.addEventListener("keydown", tus);
    return () => window.removeEventListener("keydown", tus);
  }, []);

  const gorunen = useMemo(() => {
    if (!davalar) return null;
    const sozcukler = sadelestir(arama).split(/\s+/).filter(Boolean);
    const liste = davalar.filter((d) => {
      if (yalnizBekleyen && bekleyenToplam(d) === 0) return false;
      const metin = sadelestir([d.dosya_no, d.baslik, d.muvekkil, d.dava_turu ?? ""].join(" "));
      return sozcukler.every((s) => metin.includes(s));
    });
    if (siralama === "bekleyen") {
      // Önce çelişkisi olanlar, sonra en çok bekleyen işi olanlar
      liste.sort((a, b) => b.acik_celiski - a.acik_celiski || bekleyenToplam(b) - bekleyenToplam(a));
    } else if (siralama === "dosya_no") {
      liste.sort((a, b) => a.dosya_no.localeCompare(b.dosya_no, "tr", { numeric: true }));
    }
    return liste;
  }, [davalar, arama, yalnizBekleyen, siralama]);

  const bekleyenDosya = davalar?.filter((d) => bekleyenToplam(d) > 0).length ?? 0;

  return (
    <>
      <div className="baslik-satiri">
        <div>
          <h1>Dava dosyaları</h1>
          <p className="alt-baslik">
            {kullanici.rol === "yonetici" ? "Bürodaki tüm dava dosyaları" : "Erişim yetkiniz olan dava dosyaları"}
            {davalar && <> · {davalar.length} dosya{bekleyenDosya > 0 && <>, {bekleyenDosya} dosyada bekleyen iş var</>}</>}
          </p>
        </div>
        {olusturabilir(kullanici) && (
          <Link className="dugme" href="/davalar/yeni">
            Yeni dava dosyası
          </Link>
        )}
      </div>
      {hata && <div className="bildirim hata">{hata}</div>}

      <div className="liste-arac">
        <input ref={aramaKutusu} type="text" className="arama" value={arama} onChange={(o) => setArama(o.target.value)}
               placeholder="Ara: dosya no, başlık, müvekkil, dava türü…  ( / )" aria-label="Dava dosyalarında ara" />
        <label className="sag" style={{ margin: 0, fontWeight: 500 }}>
          <input type="checkbox" checked={yalnizBekleyen} onChange={(o) => setYalnizBekleyen(o.target.checked)} />
          Yalnızca bekleyen işi olanlar
        </label>
        <select aria-label="Sıralama" value={siralama} onChange={(o) => setSiralama(o.target.value as Siralama)} style={{ width: "auto" }}>
          <option value="guncelleme">Son güncellenen önce</option>
          <option value="bekleyen">Bekleyen işi çok olan önce</option>
          <option value="dosya_no">Dosya numarasına göre</option>
        </select>
      </div>

      <div className="kart tablo-kap">
        {gorunen === null ? (
          <p className="ipucu">Yükleniyor…</p>
        ) : davalar?.length === 0 ? (
          <p className="ipucu">Erişebildiğiniz bir dava dosyası yok.</p>
        ) : gorunen.length === 0 ? (
          <p className="ipucu">
            Aramaya uyan dosya yok.{" "}
            <button className="sade kucuk" onClick={() => { setArama(""); setYalnizBekleyen(false); }}>Süzgeci temizle</button>
          </p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Dosya no</th>
                <th>Başlık</th>
                <th>Müvekkil</th>
                <th>Durum</th>
                <th>Bekleyen</th>
                <th className="sayi">Belge</th>
                <th>Son güncelleme</th>
              </tr>
            </thead>
            <tbody>
              {gorunen.map((d) => (
                <tr key={d.id}>
                  <td><Link href={`/davalar/${d.id}`}>{d.dosya_no}</Link></td>
                  <td>
                    <Link href={`/davalar/${d.id}`}>{d.baslik}</Link>
                    {d.dava_turu && <div className="ipucu">{d.dava_turu}</div>}
                  </td>
                  <td>{d.muvekkil}</td>
                  <td><span className="rozet soluk">{DAVA_DURUMU[d.durum]}</span></td>
                  <td><Bekleyen d={d} /></td>
                  <td className="sayi">
                    {d.belge_sayisi}
                    {d.islenen_belge_sayisi > 0 && <div className="ipucu">{d.islenen_belge_sayisi} işleniyor</div>}
                  </td>
                  <td>{tarih(d.guncelleme)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}

/** Dosyada bekleyen işler; her rozet ilgili sekmeye götürür. */
function Bekleyen({ d }: { d: Dava }) {
  const adres = (sekme: string) => `/davalar/${d.id}?sekme=${sekme}`;
  if (bekleyenToplam(d) === 0) {
    return d.belge_sayisi > 0
      ? <span className="rozet hazir"><Simge ad="onayla" boyut={13} /> Güncel</span>
      : <span className="ipucu">—</span>;
  }
  return (
    <span className="bekleyen-rozetler">
      {d.acik_celiski > 0 && (
        <Link className="rozet hata" href={adres("celiskiler")} title="Açık çelişki">{d.acik_celiski} çelişki</Link>
      )}
      {d.incelenmemis_bulgu > 0 && (
        <Link className="rozet uyari" href={adres("inceleme")} title="İncelenmemiş bulgu">{d.incelenmemis_bulgu} bulgu</Link>
      )}
      {d.kontrol_ocr_sayfa > 0 && (
        <Link className="rozet uyari" href={adres("belgeler")} title="Aslıyla karşılaştırılacak OCR sayfası">{d.kontrol_ocr_sayfa} OCR sayfası</Link>
      )}
      {d.onay_bekleyen_belge > 0 && (
        <Link className="rozet uyari" href={adres("ozet")} title="Özel nitelikli veri onayı bekleyen belge">{d.onay_bekleyen_belge} onay</Link>
      )}
    </span>
  );
}
