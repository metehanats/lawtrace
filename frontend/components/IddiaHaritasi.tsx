"use client";

// İddia–delil haritası: dilekçedeki her iddianın dosyadaki hangi belgelerle bağlantılı olduğu
// ve delil listesindeki kalemlerin dosyada bulunup bulunmadığı. Bağ "kanıtlar" demek değildir;
// avukatın bakacağı yeri gösterir.

import Link from "next/link";
import { DelilKalemi, DilekceHaritasi, Iddia, IddiaBagi, kaynakAdresi } from "@/lib/api";

const BAG: Record<IddiaBagi["tur"], { ad: string; sinif: string }> = {
  ek_atfi: { ad: "Ek atfı", sinif: "hazir" },
  anilan_belge: { ad: "Adı geçen belge", sinif: "" },
  ayni_deger: { ad: "Aynı değer", sinif: "" },
  celiski: { ad: "Çelişki", sinif: "hata" },
};

const DELIL: Record<DelilKalemi["tur"], { ad: string; sinif: string }> = {
  dosyada: { ad: "Dosyada var", sinif: "hazir" },
  eksik: { ad: "Dosyada bulunamadı", sinif: "uyari" },
  belge_disi: { ad: "Belge dışı delil", sinif: "soluk" },
  dis_kaynak: { ad: "Getirtilecek kayıt", sinif: "soluk" },
};

export default function IddiaHaritasi({ dilekceler }: { dilekceler: DilekceHaritasi[] }) {
  return (
    <section aria-label="İddia–delil haritası" style={{ marginTop: 14 }}>
      <h3 className="grup-baslik">İddia–delil haritası</h3>
      {dilekceler.map((d) => <Dilekce key={d.belge_id} d={d} />)}
      <p className="ipucu">
        İddialar dilekçenin AÇIKLAMALAR / SAVUNMALAR bölümünden, delil kalemleri DELİLLER bölümünden okunur.
        Bağlar metindeki izlere dayanır (ek numarası, belge adı, aynı tarih/tutar); belgenin iddiayı
        doğruladığı anlamına gelmez. Başlıksız dilekçeler haritalanmaz.
      </p>
    </section>
  );
}

function Dilekce({ d }: { d: DilekceHaritasi }) {
  const dayanaksiz = d.iddialar.filter((i) => i.dayanaksiz).length;
  const eksik = d.deliller.filter((k) => k.tur === "eksik").length;
  return (
    <div className="harita">
      <div className="sag" style={{ justifyContent: "space-between" }}>
        <strong><Link href={`/belgeler/${d.belge_id}`}>{d.belge_adi}</Link></strong>
        <span className="ipucu">
          {d.iddialar.length} iddia
          {dayanaksiz > 0 && <> · <span className="rozet uyari">{dayanaksiz} iddiada bağlantılı belge yok</span></>}
          {eksik > 0 && <> · <span className="rozet uyari">{eksik} delil dosyada bulunamadı</span></>}
        </span>
      </div>

      {d.iddialar.length > 0 && (
        <ol className="iddia-listesi">
          {d.iddialar.map((i) => <IddiaSatiri key={i.no} d={d} i={i} />)}
        </ol>
      )}

      {d.deliller.length > 0 && (
        <div className="tablo-kap">
          <table>
            <thead><tr><th>Delil listesindeki kalem</th><th>Durum</th><th>Eşleşen belge</th></tr></thead>
            <tbody>
              {d.deliller.map((k) => (
                <tr key={`${k.sayfa_no}-${k.bas}`}>
                  <td><Link href={kaynakAdresi(d.belge_id, k.sayfa_no, k.bas, k.bit)}>{k.metin}</Link></td>
                  <td><span className={`rozet ${DELIL[k.tur].sinif}`}>{DELIL[k.tur].ad}</span></td>
                  <td>
                    {k.belgeler.length
                      ? k.belgeler.map((b, n) => (
                          <span key={b.belge_id}>{n > 0 && ", "}<Link href={`/belgeler/${b.belge_id}`}>{b.belge_adi}</Link></span>
                        ))
                      : <span className="ipucu">–</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function IddiaSatiri({ d, i }: { d: DilekceHaritasi; i: Iddia }) {
  return (
    <li className={i.dayanaksiz ? "dayanaksiz" : ""}>
      <div className="alinti-kucuk">
        “{i.metin}”{" "}
        <Link className="ipucu" href={kaynakAdresi(d.belge_id, i.sayfa_no, i.bas, i.bit)}>s. {i.sayfa_no}</Link>
      </div>
      {i.dayanaksiz ? (
        <div className="ipucu" style={{ marginTop: 4 }}>
          <span className="rozet uyari">Bağlantılı belge bulunamadı</span> Dayanağı dosyada mı, kontrol edin.
        </div>
      ) : null}
      {i.baglar.length > 0 && (
        <ul className="kaynak-listesi bag-listesi">
          {i.baglar.map((b, n) => (
            <li key={n}>
              <span className={`rozet ${BAG[b.tur].sinif}`}>{BAG[b.tur].ad}</span>{" "}
              <Link href={b.sayfa_no !== null ? kaynakAdresi(b.belge_id, b.sayfa_no, b.bas, b.bit) : `/belgeler/${b.belge_id}`}>
                {b.belge_adi}
              </Link>
              {b.sayfa_no !== null && <span className="ipucu"> · s. {b.sayfa_no}</span>}
              <span className="ipucu"> — {b.aciklama}</span>
              {b.alinti && <div className="alinti-kucuk">“{b.alinti}”</div>}
            </li>
          ))}
        </ul>
      )}
    </li>
  );
}
