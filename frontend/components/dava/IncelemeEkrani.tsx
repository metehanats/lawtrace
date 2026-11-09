"use client";

// İnceleme ekranı: solda bulgular, sağda bulgunun kaynak sayfası (alıntı işaretli). Avukat kaynağa
// bakarak onaylar ya da reddeder; karar verilince sıradaki incelenmemiş bulguya geçilir.
// Klavye: J / ↓ sonraki, K / ↑ önceki, A onayla, D düzelt, R reddet.

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import EtiketSecici from "./EtiketSecici";
import { useKullanici, useOturumHatasi } from "@/components/Korumali";
import { Simge } from "@/components/Simgeler";
import VurguluMetin from "@/components/VurguluMetin";
import { api, ApiHatasi, Bulgu, BULGU_TURU, Celiski, DOGRULAMA, gonder, kaynakAdresi, Sayfa } from "@/lib/api";
import { celiskiliBulgular, DURUM_SINIFI, Islem, ocrSupheli } from "./ortak";

const KARAR_ADI = { onay: "onay", red: "ret", duzeltme: "düzeltme" } as const;

export default function IncelemeEkrani({ bulgular, celiskiler, kararVerebilir, islem, mesgul, geri }: {
  bulgular: Bulgu[]; celiskiler: Celiski[]; kararVerebilir: boolean; islem: Islem; mesgul: boolean; geri: string;
}) {
  const oturumHatasi = useOturumHatasi();
  const kullanici = useKullanici();
  const [kapsam, setKapsam] = useState<"incelenmemis" | "hepsi">(
    bulgular.some((b) => b.dogrulama_durumu === "otomatik") ? "incelenmemis" : "hepsi");
  const [seciliId, setSeciliId] = useState<string | null>(null);
  const [sayfalar, setSayfalar] = useState<Record<string, Sayfa>>({});
  const [sayfaHatasi, setSayfaHatasi] = useState<string | null>(null);
  const [etiketler, setEtiketler] = useState<Record<string, string[]>>({});
  const etiketKutusu = useRef<HTMLSelectElement>(null);

  useEffect(() => {
    api<Record<string, string[]>>("/etiketler").then(setEtiketler).catch((h) => oturumHatasi(h));
  }, [oturumHatasi]);

  const liste = useMemo(
    () => (kapsam === "hepsi" ? bulgular : bulgular.filter((b) => b.dogrulama_durumu === "otomatik")),
    [bulgular, kapsam]);
  const sira = Math.max(0, liste.findIndex((b) => b.id === seciliId));
  const secili: Bulgu | undefined = liste[sira];
  const celiskili = celiskiliBulgular(celiskiler);

  // Seçili bulgu listede yoksa (ör. karar verilip listeden düştüyse) ilkine geç
  useEffect(() => {
    if (secili && secili.id !== seciliId) setSeciliId(secili.id);
  }, [secili, seciliId]);

  const sayfaAnahtari = secili ? `${secili.belge_id}:${secili.sayfa_no}` : null;
  useEffect(() => {
    if (!secili || !sayfaAnahtari || sayfalar[sayfaAnahtari]) return;
    setSayfaHatasi(null);
    api<Sayfa>(`/belgeler/${secili.belge_id}/sayfalar/${secili.sayfa_no}`)
      .then((s) => setSayfalar((eski) => ({ ...eski, [sayfaAnahtari]: s })))
      .catch((h) => !oturumHatasi(h) && setSayfaHatasi(h instanceof Error ? h.message : "Sayfa yüklenemedi."));
  }, [secili, sayfaAnahtari, sayfalar, oturumHatasi]);

  const git = useCallback((adim: number) => {
    const hedef = liste[Math.min(liste.length - 1, Math.max(0, sira + adim))];
    if (hedef) setSeciliId(hedef.id);
  }, [liste, sira]);

  const karar = useCallback(async (k: "onay" | "red") => {
    if (!secili || !kararVerebilir || mesgul) return;
    // "İncelenmemiş" görünümünde karar verilen bulgu listeden düşer: bir sonrakine (yoksa öncekine) geçilir
    const sonraki = liste[sira + 1] ?? (kapsam === "incelenmemis" ? liste[sira - 1] : secili);
    const tamam = await islem(async () => {
      await gonder("POST", `/bulgular/${secili.id}/inceleme`, { karar: k });
      return true;
    });
    // Hata olduysa aynı bulguda kalınır (bildirim sayfanın üstünde görünür)
    if (tamam) setSeciliId(sonraki?.id ?? null);
  }, [secili, kararVerebilir, mesgul, liste, sira, kapsam, islem]);

  // Düzeltme: avukat kaynağa bakıp doğru değeri yazar; kaynak (belge, sayfa, alıntı) aynı kalır
  const [duzeltme, setDuzeltme] = useState<{ deger: string; notu: string; hata: string | null } | null>(null);
  useEffect(() => setDuzeltme(null), [secili?.id]);
  const duzeltmeAc = useCallback(() => {
    if (secili && kararVerebilir) setDuzeltme({ deger: secili.ozet, notu: "", hata: null });
  }, [secili, kararVerebilir]);

  async function duzeltmeKaydet(olay: FormEvent) {
    olay.preventDefault();
    if (!secili || !duzeltme) return;
    const sonraki = liste[sira + 1] ?? (kapsam === "incelenmemis" ? liste[sira - 1] : secili);
    try {
      await gonder("POST", `/bulgular/${secili.id}/duzeltme`, { deger: duzeltme.deger, notu: duzeltme.notu || null });
    } catch (h) {
      if (oturumHatasi(h)) return;
      setDuzeltme({ ...duzeltme, hata: h instanceof ApiHatasi ? h.message : "Düzeltilemedi." });
      return;
    }
    const onceki = secili.ozet;
    await islem(async () => true, () => `Düzeltildi: ${onceki} → ${duzeltme.deger}`);
    setDuzeltme(null);
    setSeciliId(sonraki?.id ?? null);
  }

  useEffect(() => {
    function tus(o: KeyboardEvent) {
      const hedef = o.target as HTMLElement;
      if (o.ctrlKey || o.metaKey || o.altKey || ["INPUT", "TEXTAREA", "SELECT"].includes(hedef.tagName)) return;
      const t = o.key.toLocaleLowerCase("tr-TR");
      if (t === "j" || o.key === "ArrowDown") { o.preventDefault(); git(1); }
      else if (t === "k" || o.key === "ArrowUp") { o.preventDefault(); git(-1); }
      else if (t === "a") karar("onay");
      else if (t === "r") karar("red");
      else if (t === "d") { o.preventDefault(); duzeltmeAc(); }
      else if (t === "e") { o.preventDefault(); etiketKutusu.current?.focus(); }
    }
    window.addEventListener("keydown", tus);
    return () => window.removeEventListener("keydown", tus);
  }, [git, karar, duzeltmeAc]);

  const sayfa = sayfaAnahtari ? sayfalar[sayfaAnahtari] : undefined;
  const otomatik = bulgular.filter((b) => b.dogrulama_durumu === "otomatik").length;

  return (
    <>
      <div className="baslik-satiri" style={{ marginBottom: 12 }}>
        <div>
          <h2 style={{ margin: 0 }}>Bulguları kaynağıyla incele</h2>
          <p className="ipucu" style={{ margin: 0 }}>
            {otomatik} incelenmemiş · {bulgular.length} bulgu ·{" "}
            <span className="kisayol">J</span>/<span className="kisayol">K</span> gezin
            {kararVerebilir && <> · <span className="kisayol">A</span> onayla · <span className="kisayol">D</span> düzelt · <span className="kisayol">E</span> etiket · <span className="kisayol">R</span> reddet</>}
          </p>
        </div>
        <div className="sag">
          <select aria-label="Gösterilecek bulgular" value={kapsam} style={{ width: "auto" }}
                  onChange={(o) => setKapsam(o.target.value as typeof kapsam)}>
            <option value="incelenmemis">İncelenmemiş olanlar</option>
            <option value="hepsi">Tümü</option>
          </select>
          <Link className="dugme ikincil" href={geri}>Tabloya dön</Link>
        </div>
      </div>

      {/* Kapalı dosyada da karar verilemez; onu sayfa üstündeki uyarı anlatır */}
      {!kararVerebilir && kullanici.rol === "stajyer" && (
        <div className="bildirim uyari">Stajyer hesapları bulguları görebilir ama onaylayamaz ya da reddedemez.</div>
      )}

      {liste.length === 0 ? (
        <div className="bildirim basari">
          {kapsam === "incelenmemis" ? "Tüm bulgular incelendi." : "Bu dosyada bulgu yok."}{" "}
          {kapsam === "incelenmemis" && bulgular.length > 0 && (
            <button className="sade kucuk" onClick={() => setKapsam("hepsi")}>Tümünü göster</button>
          )}
        </div>
      ) : (
        <div className="inceleme">
          <aside className="kart" style={{ padding: 0 }}>
            <div className="ipucu" style={{ padding: "8px 12px", borderBottom: "1px solid var(--cizgi)" }}>
              {sira + 1} / {liste.length}
            </div>
            <ul className="inceleme-listesi">
              {liste.map((b) => (
                <li key={b.id}>
                  <button aria-current={b.id === secili?.id} onClick={() => setSeciliId(b.id)}>
                    <div className="sag" style={{ gap: 6, justifyContent: "space-between" }}>
                      <strong>{b.ozet}</strong>
                      <span className={`rozet ${DURUM_SINIFI[b.dogrulama_durumu]}`}>{DOGRULAMA[b.dogrulama_durumu]}</span>
                    </div>
                    <div className="ipucu">
                      {BULGU_TURU[b.tur].replace(/ler$|lar$/, "")}{b.etiket ? ` · ${b.etiket}` : ""} · {b.belge_adi} s. {b.sayfa_no}
                      {celiskili.has(b.id) && <span style={{ color: "var(--hata)" }}> · çelişki</span>}
                      {b.duzeltme_onceki && <> · düzeltildi</>}
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </aside>

          {secili && (
            <section className="kart">
              <div className="baslik-satiri" style={{ marginBottom: 6 }}>
                <div>
                  <div className="ipucu">{BULGU_TURU[secili.tur]}{secili.etiket ? ` · ${secili.etiket}` : ""} · {secili.yontem === "kural" ? "Kuralla bulundu" : "Modelle bulundu"}</div>
                  <div style={{ fontSize: "1.35rem", fontWeight: 650 }}>{secili.ozet}</div>
                  {secili.duzeltme_onceki && (
                    <div className="ipucu">Avukat düzeltti · ilk okunan değer: <s>{secili.duzeltme_onceki}</s></div>
                  )}
                </div>
                <span className={`rozet ${DURUM_SINIFI[secili.dogrulama_durumu]}`}>{DOGRULAMA[secili.dogrulama_durumu]}</span>
              </div>

              {kararVerebilir && (secili.tur === "tarih" || secili.tur === "tutar") && (
                <EtiketSecici key={secili.id} ref={etiketKutusu} bulgu={secili} secenekler={etiketler[secili.tur] ?? []}
                              islem={islem} mesgul={mesgul} />
              )}
              {celiskili.get(secili.id)?.map((c) => (
                <div key={c.id} className="bildirim hata" style={{ margin: "6px 0" }}>⚠ {c.aciklama}</div>
              ))}
              {ocrSupheli(secili) && (
                <div className="bildirim uyari" style={{ margin: "6px 0" }}>
                  Bu sayfa taranmış görüntüden düşük güvenle okundu; değeri belgenin aslıyla karşılaştırın.
                </div>
              )}

              <div className="sag" style={{ justifyContent: "space-between", margin: "10px 0 6px" }}>
                <span className="ipucu">Kaynak: <strong>{secili.belge_adi}</strong> · sayfa {secili.sayfa_no}</span>
                <Link className="ipucu" href={kaynakAdresi(secili.belge_id, secili.sayfa_no, secili.karakter_baslangic, secili.karakter_bitis)}>
                  Belgede aç ↗
                </Link>
              </div>
              <div className="metin-alani" style={{ minHeight: 220, maxHeight: "48vh" }}>
                {sayfaHatasi ? <span className="ipucu">{sayfaHatasi}</span>
                  : !sayfa ? <span className="ipucu">Sayfa yükleniyor…</span>
                  : <VurguluMetin metin={sayfa.metin} bas={secili.karakter_baslangic} bit={secili.karakter_bitis} />}
              </div>

              {secili.inceleyen && (
                <p className="ipucu" style={{ margin: "8px 0 0" }}>
                  Son karar: {secili.inceleyen} ({KARAR_ADI[secili.son_karar ?? "onay"]}){secili.son_not ? ` — ${secili.son_not}` : ""}
                </p>
              )}
              {kararVerebilir && duzeltme && (
                <form className="duzeltme-formu" onSubmit={duzeltmeKaydet}
                      onKeyDown={(o) => { if (o.key === "Escape") setDuzeltme(null); }}>
                  <div className="ipucu" style={{ marginBottom: 6 }}>
                    Kaynakta gördüğünüz doğru değeri yazın. Kaynak aynı kalır; ilk okunan değer kayıtta saklanır.
                  </div>
                  <div className="sag" style={{ alignItems: "flex-start" }}>
                    <div style={{ flex: "1 1 200px" }}>
                      <label htmlFor="duzeltme-deger" style={{ marginTop: 0 }}>Doğru değer</label>
                      <input id="duzeltme-deger" type="text" autoFocus value={duzeltme.deger}
                             placeholder={secili.tur === "tarih" ? "17.03.2025" : secili.tur === "tutar" ? "386.420,50 TL" : "Ad Soyad"}
                             onChange={(o) => setDuzeltme({ ...duzeltme, deger: o.target.value, hata: null })} />
                    </div>
                    <div style={{ flex: "2 1 240px" }}>
                      <label htmlFor="duzeltme-not" style={{ marginTop: 0 }}>Not (isteğe bağlı)</label>
                      <input id="duzeltme-not" type="text" value={duzeltme.notu} placeholder="Ör. faks taramasında 8 yerine 3 okunmuş"
                             onChange={(o) => setDuzeltme({ ...duzeltme, notu: o.target.value })} />
                    </div>
                  </div>
                  {duzeltme.hata && <div className="bildirim hata" style={{ margin: "8px 0 0" }}>{duzeltme.hata}</div>}
                  <div className="form-dugmeler" style={{ marginTop: 10 }}>
                    <button type="submit" disabled={mesgul}>Düzeltmeyi kaydet</button>
                    <button type="button" className="sade" onClick={() => setDuzeltme(null)}>Vazgeç <span className="kisayol">Esc</span></button>
                  </div>
                </form>
              )}
              {kararVerebilir && !duzeltme && (
                <div className="form-dugmeler" style={{ marginTop: 12 }}>
                  <button disabled={mesgul} onClick={() => karar("onay")}>
                    <Simge ad="onayla" />Onayla <span className="kisayol">A</span>
                  </button>
                  <button className="ikincil" disabled={mesgul} onClick={duzeltmeAc}>
                    Düzelt <span className="kisayol">D</span>
                  </button>
                  <button className="tehlike" disabled={mesgul} onClick={() => karar("red")}>
                    <Simge ad="reddet" />Reddet <span className="kisayol">R</span>
                  </button>
                  <span className="ipucu" style={{ alignSelf: "center" }}>
                    Değer kaynakta farklı yazıyorsa düzeltin; bulgu hiç geçerli değilse reddedin.
                  </span>
                </div>
              )}
            </section>
          )}
        </div>
      )}
    </>
  );
}
