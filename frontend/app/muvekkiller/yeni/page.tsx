"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import MuvekkilFormu, { BOS_MUVEKKIL, MuvekkilAlanlari, muvekkilGovdesi } from "@/components/MuvekkilFormu";
import { gonder } from "@/lib/api";

function YeniMuvekkilFormu() {
  const router = useRouter();
  const parametreler = useSearchParams();

  async function kaydet(alanlar: MuvekkilAlanlari) {
    const { id } = await gonder<{ id: string }>("POST", "/muvekkiller", muvekkilGovdesi(alanlar));
    // Yeni dava formundan gelindiyse, oluşturulan müvekkil seçili olarak oraya dönülür
    router.push(parametreler.get("donus") === "yeni-dava" ? `/davalar/yeni?muvekkil=${id}` : `/muvekkiller/${id}`);
  }

  return (
    <>
      <div className="ekmek">
        <Link href="/muvekkiller">Müvekkiller</Link> / Yeni
      </div>
      <h1 style={{ marginBottom: 16 }}>Yeni müvekkil</h1>
      <MuvekkilFormu baslangic={BOS_MUVEKKIL} kaydet={kaydet} vazgec="/muvekkiller" />
    </>
  );
}

export default function YeniMuvekkilSayfasi() {
  return (
    <Suspense>
      <YeniMuvekkilFormu />
    </Suspense>
  );
}
