"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import ParolaDegistir from "@/components/ParolaDegistir";

export default function ParolaSayfasi() {
  const router = useRouter();
  const [tamam, setTamam] = useState(false);
  if (tamam) {
    return (
      <div className="kart form-kart" style={{ maxWidth: 460 }}>
        <div className="bildirim basari">Parolanız değiştirildi. Diğer cihazlardaki oturumlarınız kapatıldı.</div>
        <button onClick={() => router.push("/davalar")}>Dava dosyalarına dön</button>
      </div>
    );
  }
  return <ParolaDegistir zorunlu={false} bitti={() => setTamam(true)} />;
}
