"use client";

// Denetim kaydı: kim, ne zaman, neye ne yaptı. Yalnızca yönetici; kayıt değiştirilemez, burada yalnızca okunur.
// Başka büroya ait bir hedefin adı sunucudan hiç gelmez (yalnızca "başka büro / bulunamadı" görünür).

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import {
  api, DenetimKaydi, DenetimOzeti, EYLEM, HEDEF_TURU, ROL, tarih, YonetimKullanicisi,
} from "@/lib/api";

const GRUPLAR: { ad: string; eylemler: string[] }[] = [
  { ad: "Tümü", eylemler: [] },
  { ad: "Erişim reddi", eylemler: ["erisim_reddi"] },
  { ad: "Girişler", eylemler: ["giris", "giris_basarisiz", "cikis"] },
  { ad: "Yetki ve hesap değişiklikleri", eylemler: ["olusturma", "erisim_degisikligi", "guncelleme"] },
  { ad: "Bulgu kararları", eylemler: ["onay", "reddetme"] },
  { ad: "Belge ve analiz", eylemler: ["yukleme", "analiz", "silme"] },
  { ad: "Görüntülemeler", eylemler: ["goruntuleme"] },
  { ad: "Dışa aktarımlar", eylemler: ["disa_aktarim"] },
];

const EYLEM_SINIFI: Record<string, string> = {
  erisim_reddi: "hata", giris_basarisiz: "hata", erisim_degisikligi: "uyari", disa_aktarim: "uyari",
  olusturma: "", guncelleme: "", giris: "hazir", goruntuleme: "soluk", cikis: "soluk",
};

// Erişim reddi ve başarısız girişte "neden" farklı değerler alır
const NEDEN: Record<string, string> = {
  yetki_yok: "yetkisi yok", bulunamadi: "bulunamadı ya da başka büroya ait",
  yanlis_parola: "yanlış parola", kilitli: "hesap kilitliyken denendi", pasif_hesap: "pasif hesap",
  parola_tanimsiz: "parolası tanımlı değil",
};

const ISLEM: Record<string, string> = {
  gecici_parola: "geçici parola verildi", kilit_ac: "kilit açıldı", parola_degisimi: "parola değiştirildi",
};

type Suzgec = { kullanici: string; grup: number; baslangic: string; bitis: string };

function sorgu(s: Suzgec, ek: Record<string, string> = {}): string {
  const p = new URLSearchParams(ek);
  if (s.kullanici) p.set("kullanici", s.kullanici);
  for (const e of GRUPLAR[s.grup].eylemler) p.append("eylem", e);
  if (s.baslangic) p.set("baslangic", s.baslangic);
  if (s.bitis) p.set("bitis", s.bitis);
  return p.toString();
}

function ayrintiMetni(k: DenetimKaydi): string {
  const a = k.ayrinti;
  if (!a) return "";
  const parca: string[] = [];
  const iki = (v: unknown, ceviri: (x: unknown) => string = String) =>
    Array.isArray(v) ? `${ceviri(v[0])} → ${ceviri(v[1])}` : ceviri(v);
  const rol = (x: unknown) => (x ? ROL[x as keyof typeof ROL] ?? String(x) : "yok");
  for (const [anahtar, deger] of Object.entries(a)) {
    if (anahtar === "neden") parca.push(NEDEN[String(deger)] ?? String(deger));
    else if (anahtar === "istenen_eylem") parca.push(`istenen: ${EYLEM[String(deger)] ?? deger}`);
    else if (anahtar === "islem") parca.push(ISLEM[String(deger)] ?? String(deger));
    else if (anahtar === "rol") parca.push(`rol: ${iki(deger, rol)}`);
    else if (anahtar === "aktif") parca.push(`hesap: ${iki(deger, (x) => (x ? "aktif" : "pasif"))}`);
    else if (anahtar === "analiz_modeli") parca.push(`analiz: ${iki(deger, (x) => (x ? String(x) : "kapalı"))}`);
    else if (anahtar === "kapanan_oturum") { if (Number(deger) > 0) parca.push(`${deger} oturum kapatıldı`); }
    else if (anahtar === "hesap_kilitlendi") { if (deger) parca.push("hesap kilitlendi"); }
    else if (anahtar === "durum_kodu") continue;
    else parca.push(`${anahtar}: ${typeof deger === "object" ? JSON.stringify(deger) : String(deger)}`);
  }
  return parca.join(" · ");
}

export default function DenetimSayfasi() {
  const ben = useKullanici();
  const oturumHatasi = useOturumHatasi();
  const [kullanicilar, setKullanicilar] = useState<YonetimKullanicisi[]>([]);
  const [ozet, setOzet] = useState<DenetimOzeti | null>(null);
  const [form, setForm] = useState<Suzgec>({ kullanici: "", grup: 0, baslangic: "", bitis: "" });
  const [suzgec, setSuzgec] = useState<Suzgec>(form);
  const [kayitlar, setKayitlar] = useState<DenetimKaydi[] | null>(null);
  const [sonraki, setSonraki] = useState<number | null>(null);
  const [hata, setHata] = useState<string | null>(null);

  const hataIsle = useCallback((h: unknown) => {
    if (!oturumHatasi(h)) setHata(h instanceof Error ? h.message : "Yüklenemedi.");
  }, [oturumHatasi]);

  const getir = useCallback((s: Suzgec, once: number | null) => {
    api<{ kayitlar: DenetimKaydi[]; sonraki: number | null }>(
      `/yonetim/denetim?${sorgu(s, once ? { once: String(once) } : {})}`,
    ).then((v) => {
      setKayitlar((eski) => (once && eski ? [...eski, ...v.kayitlar] : v.kayitlar));
      setSonraki(v.sonraki);
    }).catch(hataIsle);
  }, [hataIsle]);

  useEffect(() => {
    if (ben.rol !== "yonetici") return;
    api<{ kullanicilar: YonetimKullanicisi[] }>("/yonetim/kullanicilar").then((v) => setKullanicilar(v.kullanicilar)).catch(hataIsle);
    api<DenetimOzeti>("/yonetim/denetim/ozet").then(setOzet).catch(hataIsle);
  }, [ben.rol, hataIsle]);

  useEffect(() => {
    if (ben.rol === "yonetici") getir(suzgec, null);
  }, [ben.rol, suzgec, getir]);

  function uygula(olay: FormEvent) {
    olay.preventDefault();
    setHata(null);
    setKayitlar(null);
    setSuzgec({ ...form });
  }

  if (ben.rol !== "yonetici") return <div className="bildirim hata">Bu sayfa yalnızca büro yöneticisine açıktır.</div>;

  return (
    <>
      <div className="ekmek"><Link href="/yonetim">Yönetim</Link> / Denetim kaydı</div>
      <div className="baslik-satiri">
        <div>
          <h1>Denetim kaydı</h1>
          <p className="alt-baslik">Kim, ne zaman, neye ne yaptı. Kayıtlar değiştirilemez; bu sayfayı açmanız da kayda geçer.</p>
        </div>
        <a className="dugme ikincil" href={`/api/yonetim/denetim/disa-aktar?${sorgu(suzgec)}`} download>
          CSV indir
        </a>
      </div>

      {ozet && <OzetKartlari ozet={ozet} />}
      <div className="bosluk" />

      <form className="kart" onSubmit={uygula}>
        <div className="suzgec-izgara">
          <div>
            <label htmlFor="s_kullanici">Kullanıcı</label>
            <select id="s_kullanici" value={form.kullanici} onChange={(o) => setForm({ ...form, kullanici: o.target.value })}>
              <option value="">Herkes</option>
              {kullanicilar.map((k) => <option key={k.id} value={k.id}>{k.ad_soyad}{k.aktif ? "" : " (pasif)"}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="s_grup">Eylem</label>
            <select id="s_grup" value={form.grup} onChange={(o) => setForm({ ...form, grup: Number(o.target.value) })}>
              {GRUPLAR.map((g, i) => <option key={g.ad} value={i}>{g.ad}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="s_bas">Başlangıç</label>
            <input id="s_bas" type="date" value={form.baslangic} onChange={(o) => setForm({ ...form, baslangic: o.target.value })} />
          </div>
          <div>
            <label htmlFor="s_bit">Bitiş</label>
            <input id="s_bit" type="date" value={form.bitis} onChange={(o) => setForm({ ...form, bitis: o.target.value })} />
          </div>
        </div>
        <div className="form-dugmeler" style={{ marginTop: 12 }}>
          <button type="submit">Süz</button>
          <button type="button" className="sade" onClick={() => {
            const bos = { kullanici: "", grup: 0, baslangic: "", bitis: "" };
            setForm(bos);
            setKayitlar(null);
            setSuzgec(bos);
          }}>Temizle</button>
        </div>
      </form>
      <div className="bosluk" />

      <div className="kart tablo-kap">
        {hata && <div className="bildirim hata">{hata}</div>}
        {kayitlar === null ? <p className="ipucu">Yükleniyor…</p> : kayitlar.length === 0 ? (
          <p className="ipucu">Bu süzgeçle kayıt yok.</p>
        ) : (
          <table>
            <thead><tr><th>Zaman</th><th>Kullanıcı</th><th>Eylem</th><th>Hedef</th><th>Ayrıntı</th><th>IP</th></tr></thead>
            <tbody>
              {kayitlar.map((k) => (
                <tr key={k.id}>
                  <td style={{ whiteSpace: "nowrap" }}>{tarih(k.zaman)}</td>
                  <td>{k.kullanici_adi ?? <span className="ipucu">—</span>}</td>
                  <td><span className={`rozet ${EYLEM_SINIFI[k.eylem] ?? ""}`}>{EYLEM[k.eylem] ?? k.eylem}</span></td>
                  <td><Hedef k={k} /></td>
                  <td className="ipucu">{ayrintiMetni(k)}</td>
                  <td className="ipucu">{k.ip_adresi ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        {sonraki !== null && (
          <button className="ikincil" style={{ marginTop: 12 }} onClick={() => getir(suzgec, sonraki)}>Daha eski kayıtlar</button>
        )}
      </div>
    </>
  );
}

function Hedef({ k }: { k: DenetimKaydi }) {
  const tur = HEDEF_TURU[k.hedef_tur] ?? k.hedef_tur;
  const adres = k.hedef_belge_id ? `/belgeler/${k.hedef_belge_id}` : k.hedef_dava_id ? `/davalar/${k.hedef_dava_id}` : null;
  return (
    <>
      <div className="ipucu">{tur}</div>
      {k.hedef_adi ? (adres ? <Link href={adres}>{k.hedef_adi}</Link> : <span>{k.hedef_adi}</span>)
        : k.hedef_id ? <span className="ipucu" title={k.hedef_id}>Bulunamadı ya da başka büroya ait</span> : null}
    </>
  );
}

function OzetKartlari({ ozet }: { ozet: DenetimOzeti }) {
  const say = (e: string) => ozet.eylemler[e] ?? 0;
  return (
    <div className="ozet-izgara">
      <div className="kart">
        <div className="ipucu">Son 24 saat · erişim reddi</div>
        <div className="ozet-sayi">{say("erisim_reddi")}</div>
        {ozet.reddedilen_kullanicilar.map((r) => (
          <div key={r.kullanici_id ?? "?"} className="ipucu">{r.ad_soyad ?? "Bilinmeyen"}: {r.sayi} · son {tarih(r.son_zaman)}</div>
        ))}
      </div>
      <div className="kart">
        <div className="ipucu">Son 24 saat · başarısız giriş</div>
        <div className="ozet-sayi">{say("giris_basarisiz")}</div>
        {ozet.kilitlenen_hesaplar.map((k) => (
          <div key={k.kullanici_id} className="ipucu"><span className="rozet hata">Kilitlendi</span> {k.ad_soyad} · {tarih(k.zaman)}</div>
        ))}
      </div>
      <div className="kart">
        <div className="ipucu">Son 24 saat · yetki ve hesap değişikliği</div>
        <div className="ozet-sayi">{say("erisim_degisikligi") + say("olusturma")}</div>
        <div className="ipucu">Dışa aktarım: {say("disa_aktarim")} · Giriş: {say("giris")}</div>
      </div>
    </div>
  );
}
