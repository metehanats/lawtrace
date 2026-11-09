"use client";

import { useEffect, useRef } from "react";

/** Sayfa metninde [bas, bit) aralığını işaretler ve görünür alana kaydırır (kaynak alıntı). */
export default function VurguluMetin({ metin, bas, bit }: { metin: string; bas: number | null; bit: number | null }) {
  const isaret = useRef<HTMLElement>(null);
  useEffect(() => {
    const el = isaret.current;
    if (!el) return;
    // Yalnızca metin kutusunun içi kaydırılır; sayfanın kendisi zıplamasın (inceleme ekranı)
    const kutu = el.closest<HTMLElement>(".metin-alani");
    if (kutu) kutu.scrollTo({ top: el.offsetTop - kutu.clientHeight / 2, behavior: "smooth" });
    else el.scrollIntoView({ block: "center" });
  }, [metin, bas]);
  if (bas === null || bit === null || bas < 0 || bit > metin.length || bas >= bit) return <>{metin}</>;
  return (
    <>
      {metin.slice(0, bas)}
      <mark ref={isaret} className="kaynak">{metin.slice(bas, bit)}</mark>
      {metin.slice(bit)}
    </>
  );
}
