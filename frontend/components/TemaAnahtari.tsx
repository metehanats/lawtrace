"use client";

// Üst çubuktaki tema anahtarı: güneş/ay düğmeli kayan anahtar ve yanında "Otomatik" (Windows ayarına uy).
// Anahtara dokunmak Otomatik'i kapatır ve seçimi sabitler. Seçim yalnızca bu tarayıcıda saklanır
// (localStorage "tema": sistem | acik | koyu); ilk uygulama app/layout.tsx'teki betikte.

import { useEffect, useState } from "react";
import { Simge } from "@/components/Simgeler";

type Tema = "sistem" | "acik" | "koyu";

const sistemKoyu = () => matchMedia("(prefers-color-scheme: dark)").matches;

function uygula(koyu: boolean) {
  const kok = document.documentElement;
  // Renkler yumuşak geçsin; geçiş sınıfı yalnızca değişim anında durur (her hover'da değil)
  kok.classList.add("tema-gecis");
  kok.dataset.tema = koyu ? "koyu" : "acik";
  window.setTimeout(() => kok.classList.remove("tema-gecis"), 350);
}

function kaydet(tema: Tema) {
  try {
    localStorage.setItem("tema", tema);
  } catch {
    // Gizli pencere vb.: seçim yalnızca bu sayfa için geçerli olur
  }
}

export default function TemaAnahtari() {
  const [otomatik, setOtomatik] = useState(true);
  const [koyu, setKoyu] = useState(false);

  useEffect(() => {
    let t: Tema = "sistem";
    try {
      const s = localStorage.getItem("tema");
      if (s === "acik" || s === "koyu") t = s;
    } catch {
      // okunamazsa Otomatik
    }
    setOtomatik(t === "sistem");
    setKoyu(document.documentElement.dataset.tema === "koyu");
  }, []);

  // Otomatik'teyken Windows ayarı değişirse hemen uy
  useEffect(() => {
    if (!otomatik) return;
    const sorgu = matchMedia("(prefers-color-scheme: dark)");
    const degisti = () => {
      setKoyu(sorgu.matches);
      uygula(sorgu.matches);
    };
    sorgu.addEventListener("change", degisti);
    return () => sorgu.removeEventListener("change", degisti);
  }, [otomatik]);

  function anahtar() {
    const yeni = !koyu;
    setKoyu(yeni);
    setOtomatik(false);
    kaydet(yeni ? "koyu" : "acik");
    uygula(yeni);
  }

  function otomatikDegistir(acik: boolean) {
    setOtomatik(acik);
    if (acik) {
      kaydet("sistem");
      setKoyu(sistemKoyu());
      uygula(sistemKoyu());
    } else {
      kaydet(koyu ? "koyu" : "acik");
    }
  }

  return (
    <span className="tema-anahtari">
      <button type="button" role="switch" aria-checked={koyu} aria-label="Koyu tema" className="anahtar"
              title={koyu ? "Açık temaya geç" : "Koyu temaya geç"} onClick={anahtar}>
        <span className="anahtar-topuz"><Simge ad={koyu ? "koyu" : "acik"} boyut={13} /></span>
      </button>
      <label className="otomatik" title="Windows'un açık/koyu ayarına uy">
        <input type="checkbox" checked={otomatik} onChange={(o) => otomatikDegistir(o.target.checked)} />
        Otomatik
      </label>
    </span>
  );
}
