"use client";

// Büro yönetimi: büro adı, analiz ayarı ve kullanıcılar. Yalnızca yönetici görür; yetki sunucuda da denetlenir.
// Geçici parola yalnızca üretildiği anda bir kez gösterilir; sayfa yenilenince kaybolur.

import Link from "next/link";
import { FormEvent, Fragment, useCallback, useEffect, useRef, useState } from "react";
import { Rol, Simge } from "@/components/Simgeler";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import {
  api, ApiHatasi, BuroAyarlari, gonder, Kullanici, ROL, tarih, YedekDurumu, YonetimKullanicisi,
} from "@/lib/api";

type Bildirim = { tur: "hata" | "basari"; mesaj: string } | null;
type Gecici = { id: string; kime: string; e_posta: string; parola: string } | null;

export default function YonetimSayfasi() {
  const ben = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [buro, setBuro] = useState<BuroAyarlari | null>(null);
  const [yedek, setYedek] = useState<YedekDurumu | null>(null);
  const [kullanicilar, setKullanicilar] = useState<YonetimKullanicisi[] | null>(null);
  const [bildirim, setBildirim] = useState<Bildirim>(null);
  const [gecici, setGecici] = useState<Gecici>(null);
  const [mesgul, setMesgul] = useState(false);

  const yukle = useCallback(() => {
    const hata = (h: unknown) => {
      if (!oturumHatasi(h)) setBildirim({ tur: "hata", mesaj: h instanceof Error ? h.message : "Yüklenemedi." });
    };
    api<BuroAyarlari>("/yonetim/buro").then(setBuro).catch(hata);
    api<YedekDurumu>("/yonetim/yedek").then(setYedek).catch(hata);
    api<{ kullanicilar: YonetimKullanicisi[] }>("/yonetim/kullanicilar").then((v) => setKullanicilar(v.kullanicilar)).catch(hata);
  }, [oturumHatasi]);

  useEffect(() => {
    if (ben.rol === "yonetici") yukle();
  }, [ben.rol, yukle]);

  async function islem<T>(fn: () => Promise<T>, basari?: (v: T) => string | null): Promise<T | undefined> {
    setBildirim(null);
    setMesgul(true);
    try {
      const sonuc = await fn();
      const mesaj = basari?.(sonuc);
      if (mesaj) setBildirim({ tur: "basari", mesaj });
      yukle();
      return sonuc;
    } catch (h) {
      if (!oturumHatasi(h)) setBildirim({ tur: "hata", mesaj: h instanceof ApiHatasi ? h.message : "İşlem yapılamadı." });
    } finally {
      setMesgul(false);
    }
  }

  if (ben.rol !== "yonetici") {
    return <div className="bildirim hata">Bu sayfa yalnızca büro yöneticisine açıktır.</div>;
  }

  return (
    <>
      <div className="baslik-satiri">
        <div>
          <h1>Yönetim</h1>
          <p className="alt-baslik">{buro?.ad ?? ben.buro_adi} · kullanıcılar ve büro ayarları</p>
        </div>
        <Link className="dugme ikincil" href="/yonetim/denetim">Denetim kaydı</Link>
      </div>

      {bildirim && <div className={`bildirim ${bildirim.tur}`} role="status">{bildirim.mesaj}</div>}

      {buro && <BuroAdi ad={buro.ad} mesgul={mesgul} kaydet={(ad) => islem(
        async () => { await gonder("PUT", "/yonetim/buro/ad", { ad }); return true; }, () => "Büro adı değiştirildi.",
      )} />}
      <div className="bosluk" />
      {buro && <AnalizAyari buro={buro} mesgul={mesgul} ayarla={(model) => islem(
        () => gonder("PUT", "/yonetim/buro/analiz", { analiz_modeli: model }),
        () => (model ? `Analiz açıldı (${model}).` : "Analiz kapatıldı."),
      )} />}
      <div className="bosluk" />
      {yedek && <YedekKarti y={yedek} />}
      <div className="bosluk" />

      <div className="kart tablo-kap">
        <h2>Kullanıcılar {kullanicilar && <span className="ipucu">({kullanicilar.filter((k) => k.aktif).length} aktif)</span>}</h2>
        {kullanicilar === null ? <p className="ipucu">Yükleniyor…</p> : (
          <table>
            <thead>
              <tr><th>Kullanıcı</th><th>Rol</th><th>Durum</th><th>Son giriş</th><th /></tr>
            </thead>
            <tbody>
              {kullanicilar.map((k) => (
                <Fragment key={k.id}>
                <KullaniciSatiri k={k} kendisi={k.id === ben.id} mesgul={mesgul}
                  bilgiDegistir={(govde) => islem(
                    async () => { await gonder("PATCH", `/yonetim/kullanicilar/${k.id}`, govde); return true; },
                    () => govde.e_posta.trim().toLowerCase() !== k.e_posta && k.id !== ben.id
                      ? `${govde.ad_soyad}: bilgiler kaydedildi. E-posta değiştiği için açık oturumları kapatıldı; yeni e-postasıyla girecek.`
                      : `${govde.ad_soyad}: bilgiler kaydedildi.`).then(Boolean)}
                  rolDegistir={(rol) => islem(() => gonder("PATCH", `/yonetim/kullanicilar/${k.id}`, { rol }),
                                              () => `${k.ad_soyad}: rol ${ROL[rol]} yapıldı; açık oturumları kapatıldı.`)}
                  aktiflik={(aktif) => {
                    if (!aktif && !confirm(`${k.ad_soyad} pasifleştirilsin mi? Açık oturumları kapanır ve giriş yapamaz.`)) return;
                    islem(() => gonder("PATCH", `/yonetim/kullanicilar/${k.id}`, { aktif }),
                          () => `${k.ad_soyad} ${aktif ? "yeniden etkinleştirildi" : "pasifleştirildi"}.`);
                  }}
                  kilitAc={() => islem(() => gonder("POST", `/yonetim/kullanicilar/${k.id}/kilit-ac`),
                                       () => `${k.ad_soyad} hesabının kilidi açıldı.`)}
                  geciciParola={async () => {
                    if (!confirm(`${k.ad_soyad} için yeni geçici parola üretilsin mi? Mevcut parolası geçersiz olur ve açık oturumları kapanır.`)) return;
                    const s = await islem(() => gonder<{ gecici_parola: string }>("POST", `/yonetim/kullanicilar/${k.id}/gecici-parola`));
                    if (s) setGecici({ id: k.id, kime: k.ad_soyad, e_posta: k.e_posta, parola: s.gecici_parola });
                  }} />
                {/* Parola, üretildiği kişinin satırının hemen altında görünür (sayfa oraya kayar) */}
                {gecici?.id === k.id && (
                  <tr className="gecici-satir">
                    <td colSpan={5}><GeciciParolaKutusu gecici={gecici} kapat={() => setGecici(null)} /></td>
                  </tr>
                )}
                </Fragment>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="bosluk" />

      <YeniKullanici mesgul={mesgul} olustur={async (govde) => {
        const s = await islem(() => gonder<{ id: string; gecici_parola: string }>("POST", "/yonetim/kullanicilar", govde));
        if (s) setGecici({ id: s.id, kime: govde.ad_soyad, e_posta: govde.e_posta.trim().toLowerCase(), parola: s.gecici_parola });
        return Boolean(s);
      }} />
    </>
  );
}

function BuroAdi({ ad, mesgul, kaydet }: {
  ad: string; mesgul: boolean; kaydet: (ad: string) => Promise<unknown>;
}) {
  const [duzenleniyor, setDuzenleniyor] = useState(false);
  const [yeni, setYeni] = useState(ad);

  async function gonderForm(olay: FormEvent) {
    olay.preventDefault();
    if (await kaydet(yeni)) setDuzenleniyor(false);
  }

  return (
    <div className="kart">
      <h2>Büro</h2>
      {duzenleniyor ? (
        <form className="erisim-ekle" onSubmit={gonderForm}>
          <input aria-label="Büro adı" type="text" required maxLength={200} value={yeni} autoFocus
                 onChange={(o) => setYeni(o.target.value)} />
          <button type="submit" disabled={mesgul || !yeni.trim() || yeni.trim() === ad}>Kaydet</button>
          <button type="button" className="ikincil" onClick={() => { setYeni(ad); setDuzenleniyor(false); }}>Vazgeç</button>
        </form>
      ) : (
        <p className="sag" style={{ margin: 0 }}>
          <strong>{ad}</strong>
          <button className="ikincil kucuk" disabled={mesgul} onClick={() => setDuzenleniyor(true)}>Adı değiştir</button>
        </p>
      )}
    </div>
  );
}

function AnalizAyari({ buro, mesgul, ayarla }: {
  buro: BuroAyarlari; mesgul: boolean; ayarla: (model: string | null) => void;
}) {
  const [secim, setSecim] = useState(buro.analiz_modeli ?? buro.yerel_modeller?.[0] ?? "");
  return (
    <div className="kart">
      <h2>Belge analizi</h2>
      <p style={{ margin: "0 0 10px" }}>
        Durum:{" "}
        {buro.analiz_modeli
          ? <span className="rozet hazir">Açık · {buro.analiz_modeli}</span>
          : <span className="rozet soluk">Kapalı</span>}
      </p>
      <p className="ipucu" style={{ marginTop: 0 }}>
        Analiz yalnızca bu bilgisayarda çalışan yerel modelle yapılır; belgeler dışarı gönderilmez.
        Bulut modelleri KVKK değerlendirmesi tamamlanana kadar kullanılamaz.
      </p>
      {buro.yerel_modeller === null ? (
        <div className="bildirim uyari">Yerel model sunucusuna (Ollama) ulaşılamadı. Analizi açmak için önce Ollama&apos;nın çalıştığından emin olun.</div>
      ) : buro.yerel_modeller.length === 0 ? (
        <div className="bildirim uyari">Bu bilgisayarda kurulu yerel model yok.</div>
      ) : (
        <div className="erisim-ekle">
          <select aria-label="Yerel model" value={secim} onChange={(o) => setSecim(o.target.value)}>
            {buro.yerel_modeller.map((m) => <option key={m} value={m}>{m.replace(/^ollama:/, "")}</option>)}
          </select>
          <button disabled={mesgul || !secim || secim === buro.analiz_modeli} onClick={() => ayarla(secim)}>
            {buro.analiz_modeli ? "Modeli değiştir" : "Analizi aç"}
          </button>
        </div>
      )}
      {buro.analiz_modeli && (
        <button className="ikincil" style={{ marginTop: 10 }} disabled={mesgul} onClick={() => ayarla(null)}>
          Analizi kapat
        </button>
      )}
    </div>
  );
}

function YedekKarti({ y }: { y: YedekDurumu }) {
  const hata = y.son_deneme?.durum === "hata" ? y.son_deneme : null;
  return (
    <div className="kart">
      <h2>Yedekleme</h2>
      {y.son_basarili ? (
        <p style={{ margin: "0 0 6px" }}>
          Son başarılı yedek: <strong>{tarih(y.son_basarili.zaman)}</strong>{" "}
          <span className="rozet hazir">Doğrulandı</span>{" "}
          <span className="ipucu">
            ({y.son_basarili.dogrulanan_belge} belge geri yüklenip çözüldü · saklanan yedek: {y.yedek_sayisi})
          </span>
        </p>
      ) : <p style={{ margin: "0 0 6px" }}>Henüz otomatik yedek alınmadı.</p>}
      {hata && <div className="bildirim hata">Son deneme başarısız ({tarih(hata.zaman)}): {hata.mesaj}</div>}
      {y.uyari && !hata && (
        <div className="bildirim uyari">Son 36 saatte başarılı yedek yok. Bilgisayar kapalı kalmış ya da görev çalışmamış olabilir.</div>
      )}
      <p className="ipucu" style={{ marginBottom: 0 }}>
        Yedek her gün 18:30&apos;da alınır, tam doğrulanır ve en yeni 14 yedek saklanır. Yedekleri açmak için
        şifreleme anahtarı gerekir; anahtarın yedeği parola yöneticisinde durmalı.
      </p>
    </div>
  );
}

type KullaniciBilgisi = { ad_soyad: string; e_posta: string };

function KullaniciSatiri({ k, kendisi, mesgul, bilgiDegistir, rolDegistir, aktiflik, kilitAc, geciciParola }: {
  k: YonetimKullanicisi; kendisi: boolean; mesgul: boolean;
  bilgiDegistir: (govde: KullaniciBilgisi) => Promise<boolean>;
  rolDegistir: (rol: Kullanici["rol"]) => void; aktiflik: (aktif: boolean) => void;
  kilitAc: () => void; geciciParola: () => void;
}) {
  const [duzenleniyor, setDuzenleniyor] = useState(false);
  const [bilgi, setBilgi] = useState<KullaniciBilgisi>({ ad_soyad: k.ad_soyad, e_posta: k.e_posta });

  async function kaydet(olay: FormEvent) {
    olay.preventDefault();
    if (bilgi.e_posta.trim().toLowerCase() !== k.e_posta && !kendisi
        && !confirm(`${k.ad_soyad} kullanıcısının e-postası (giriş adı) değişecek ve açık oturumları kapanacak. Devam edilsin mi?`)) return;
    if (await bilgiDegistir(bilgi)) setDuzenleniyor(false);
  }

  return (
    <tr style={k.aktif ? undefined : { opacity: 0.6 }}>
      <td>
        {duzenleniyor ? (
          <form className="satir-duzenle" onSubmit={kaydet}>
            <input aria-label="Ad soyad" type="text" required minLength={2} maxLength={200} value={bilgi.ad_soyad} autoFocus
                   onChange={(o) => setBilgi((b) => ({ ...b, ad_soyad: o.target.value }))} />
            <input aria-label="E-posta" type="email" required maxLength={254} value={bilgi.e_posta}
                   onChange={(o) => setBilgi((b) => ({ ...b, e_posta: o.target.value }))} />
            <span className="sag">
              <button type="submit" className="kucuk" disabled={mesgul}>Kaydet</button>
              <button type="button" className="ikincil kucuk"
                      onClick={() => { setBilgi({ ad_soyad: k.ad_soyad, e_posta: k.e_posta }); setDuzenleniyor(false); }}>
                Vazgeç
              </button>
            </span>
          </form>
        ) : (
          <>
            <strong>{k.ad_soyad}</strong>{kendisi && <span className="ipucu"> (siz)</span>}
            <div className="ipucu">{k.e_posta}</div>
          </>
        )}
      </td>
      <td>
        {kendisi ? <Rol rol={k.rol} /> : (
          // Açılır listede simge gösterilemez; seçili rolün simgesi listenin önünde durur
          <span className="sag" style={{ gap: 6, flexWrap: "nowrap" }}>
            <Simge ad={k.rol} boyut={16} />
            <select aria-label={`${k.ad_soyad} rolü`} value={k.rol} disabled={mesgul || !k.aktif}
                    onChange={(o) => rolDegistir(o.target.value as Kullanici["rol"])} style={{ width: "auto" }}>
              {(Object.keys(ROL) as Kullanici["rol"][]).map((r) => <option key={r} value={r}>{ROL[r]}</option>)}
            </select>
          </span>
        )}
      </td>
      <td>
        <span className="sag">
          {k.aktif ? <span className="rozet hazir">Aktif</span> : <span className="rozet soluk">Pasif</span>}
          {k.kilitli && <span className="rozet hata" title={k.kilit_bitis ? `Kilit bitişi: ${tarih(k.kilit_bitis)}` : undefined}>Kilitli</span>}
          {k.parola_degismeli && <span className="rozet uyari">Geçici parola</span>}
          {!k.parolasi_var && <span className="rozet uyari">Parolası yok</span>}
        </span>
      </td>
      <td>{k.son_giris ? tarih(k.son_giris) : <span className="ipucu">Hiç</span>}</td>
      <td>
        <span className="sag">
          {!duzenleniyor && (
            <button className="ikincil kucuk" disabled={mesgul}
                    onClick={() => { setBilgi({ ad_soyad: k.ad_soyad, e_posta: k.e_posta }); setDuzenleniyor(true); }}>
              Düzenle
            </button>
          )}
          {!kendisi && (
            <>
            {k.kilitli && <button className="ikincil kucuk" disabled={mesgul} onClick={kilitAc}>Kilidi aç</button>}
            {k.aktif && <button className="ikincil kucuk" disabled={mesgul} onClick={geciciParola}>Geçici parola</button>}
            <button className={`kucuk ${k.aktif ? "tehlike" : "ikincil"}`} disabled={mesgul} onClick={() => aktiflik(!k.aktif)}>
              {k.aktif ? "Pasifleştir" : "Etkinleştir"}
            </button>
            </>
          )}
        </span>
      </td>
    </tr>
  );
}

function YeniKullanici({ mesgul, olustur }: {
  mesgul: boolean;
  olustur: (govde: { ad_soyad: string; e_posta: string; rol: Kullanici["rol"] }) => Promise<boolean>;
}) {
  const [adSoyad, setAdSoyad] = useState("");
  const [ePosta, setEPosta] = useState("");
  const [rol, setRol] = useState<Kullanici["rol"]>("avukat");

  async function gonderForm(olay: FormEvent) {
    olay.preventDefault();
    if (await olustur({ ad_soyad: adSoyad, e_posta: ePosta, rol })) {
      setAdSoyad("");
      setEPosta("");
      setRol("avukat");
    }
  }

  return (
    <form className="kart form-kart" onSubmit={gonderForm}>
      <h2>Yeni kullanıcı</h2>
      <p className="ipucu" style={{ marginTop: 0 }}>
        Hesap tek kullanımlık geçici bir parolayla açılır. Parolayı kullanıcıya güvenli bir yoldan iletin;
        ilk girişte kendi parolasını belirlemesi istenir.
      </p>
      <div className="form-izgara">
        <div>
          <label htmlFor="ad_soyad">Ad soyad</label>
          <input id="ad_soyad" type="text" required minLength={2} value={adSoyad} onChange={(o) => setAdSoyad(o.target.value)} />
        </div>
        <div>
          <label htmlFor="yeni_e_posta">E-posta</label>
          <input id="yeni_e_posta" type="email" required value={ePosta} onChange={(o) => setEPosta(o.target.value)} />
        </div>
        <div>
          <label htmlFor="rol">Rol</label>
          <select id="rol" value={rol} onChange={(o) => setRol(o.target.value as Kullanici["rol"])}>
            {(Object.keys(ROL) as Kullanici["rol"][]).map((r) => <option key={r} value={r}>{ROL[r]}</option>)}
          </select>
        </div>
      </div>
      <div className="form-dugmeler">
        <button type="submit" disabled={mesgul}>Hesabı aç</button>
      </div>
    </form>
  );
}

function GeciciParolaKutusu({ gecici, kapat }: { gecici: NonNullable<Gecici>; kapat: () => void }) {
  const [kopyalandi, setKopyalandi] = useState(false);
  const kutu = useRef<HTMLDivElement>(null);
  // Yeni hesap formu sayfanın altında; kutu tablodaki satırda açılınca görünür alana getirilir
  useEffect(() => kutu.current?.scrollIntoView({ block: "center", behavior: "smooth" }), [gecici.parola]);
  return (
    <div ref={kutu} className="bildirim uyari" role="alert" style={{ margin: 0 }}>
      <strong>{gecici.kime}</strong> ({gecici.e_posta}) için geçici parola:
      <div className="sag" style={{ margin: "8px 0" }}>
        <code className="gecici-parola">{gecici.parola}</code>
        <button className="ikincil kucuk" onClick={() => navigator.clipboard.writeText(gecici.parola).then(() => setKopyalandi(true))}>
          {kopyalandi ? "Kopyalandı" : "Kopyala"}
        </button>
      </div>
      Bu parola <strong>yalnızca şimdi</strong> gösteriliyor ve hiçbir yere kaydedilmiyor. Kullanıcıya e-posta
      dışında güvenli bir yoldan (yüz yüze, telefon) iletin.{" "}
      <button className="sade kucuk" onClick={kapat}>Gizle</button>
    </div>
  );
}
