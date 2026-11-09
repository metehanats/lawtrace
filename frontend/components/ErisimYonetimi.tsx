"use client";

// Dava dosyasına kimin erişebileceği. Herkes listeyi görür; yalnızca büro yöneticisi
// ya da dosya sorumlusu değiştirebilir (API de aynı kuralı uygular).

import { useCallback, useEffect, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import { Rol } from "@/components/Simgeler";
import { api, ApiHatasi, BuroKullanicisi, Erisim, ERISIM_ROLU, ErisimRolu, gonder, ROL } from "@/lib/api";

export default function ErisimYonetimi({ davaId }: { davaId: string }) {
  const ben = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [veri, setVeri] = useState<{ erisimler: Erisim[]; yonetebilir: boolean } | null>(null);
  const [kullanicilar, setKullanicilar] = useState<BuroKullanicisi[]>([]);
  const [secili, setSecili] = useState("");
  const [rol, setRol] = useState<ErisimRolu>("inceleyen");
  const [hata, setHata] = useState<string | null>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(() => {
    api<{ erisimler: Erisim[]; yonetebilir: boolean }>(`/davalar/${davaId}/erisimler`)
      .then((v) => {
        setVeri(v);
        if (v.yonetebilir) return api<{ kullanicilar: BuroKullanicisi[] }>("/kullanicilar").then((k) => setKullanicilar(k.kullanicilar));
      })
      .catch((h) => !oturumHatasi(h) && setHata(h.message));
  }, [davaId, oturumHatasi]);

  useEffect(yukle, [yukle]);

  async function islem(fn: () => Promise<unknown>) {
    setHata(null);
    setMesgul(true);
    try {
      await fn();
      yukle();
    } catch (h) {
      if (!oturumHatasi(h)) setHata(h instanceof ApiHatasi ? h.message : "İşlem yapılamadı.");
    } finally {
      setMesgul(false);
    }
  }

  if (!veri) return null;
  const erisimiOlanlar = new Set(veri.erisimler.map((e) => e.kullanici_id));
  const eklenebilir = kullanicilar.filter((k) => !erisimiOlanlar.has(k.id));

  return (
    <div className="kart tablo-kap">
      <h2>Erişim</h2>
      {hata && <div className="bildirim hata" role="alert">{hata}</div>}
      <table>
        <thead>
          <tr><th>Kişi</th><th>Rolü</th><th>Bu dosyada</th>{veri.yonetebilir && <th />}</tr>
        </thead>
        <tbody>
          {veri.erisimler.map((e) => (
            <tr key={e.kullanici_id}>
              <td>{e.ad_soyad}{e.kullanici_id === ben.id && <span className="ipucu"> (siz)</span>}</td>
              <td className="ipucu"><Rol rol={e.rol} /></td>
              <td>
                {veri.yonetebilir ? (
                  <select aria-label={`${e.ad_soyad} için erişim rolü`} value={e.erisim_rolu} disabled={mesgul}
                          style={{ width: "auto" }}
                          onChange={(o) => islem(() => gonder("PUT", `/davalar/${davaId}/erisimler/${e.kullanici_id}`, { rol: o.target.value }))}>
                    <option value="sorumlu">Sorumlu</option>
                    <option value="inceleyen">İnceleyen</option>
                  </select>
                ) : (
                  <span className="rozet soluk">{ERISIM_ROLU[e.erisim_rolu]}</span>
                )}
              </td>
              {veri.yonetebilir && (
                <td style={{ textAlign: "right" }}>
                  <button className="tehlike" disabled={mesgul}
                          onClick={() => islem(() => gonder("DELETE", `/davalar/${davaId}/erisimler/${e.kullanici_id}`))}>
                    Kaldır
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      {veri.yonetebilir && (
        eklenebilir.length > 0 ? (
          <form className="erisim-ekle" onSubmit={(o) => {
            o.preventDefault();
            if (secili) islem(() => gonder("PUT", `/davalar/${davaId}/erisimler/${secili}`, { rol })).then(() => setSecili(""));
          }}>
            <select aria-label="Erişim verilecek kişi" value={secili} onChange={(o) => setSecili(o.target.value)}>
              <option value="">Kişi seçin</option>
              {eklenebilir.map((k) => <option key={k.id} value={k.id}>{k.ad_soyad} ({ROL[k.rol]})</option>)}
            </select>
            <select aria-label="Erişim rolü" value={rol} onChange={(o) => setRol(o.target.value as ErisimRolu)}>
              <option value="inceleyen">İnceleyen</option>
              <option value="sorumlu">Sorumlu</option>
            </select>
            <button type="submit" disabled={!secili || mesgul}>Erişim ver</button>
          </form>
        ) : (
          <p className="ipucu">Bürodaki herkesin bu dosyaya erişimi var.</p>
        )
      )}
      <p className="ipucu">
        Sorumlular dosyanın erişimlerini yönetebilir; inceleyenler yalnızca görüntüler ve belge yükler. Büro yöneticileri
        tüm dosyaları görür.
      </p>
    </div>
  );
}
