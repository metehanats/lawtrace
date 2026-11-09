import { BELGE_DURUMU, BelgeDurumu } from "@/lib/api";

const SINIF: Record<BelgeDurumu, string> = { yuklendi: "soluk", isleniyor: "", hazir: "hazir", hata: "hata" };

export function BelgeDurumRozeti({ durum }: { durum: BelgeDurumu }) {
  return <span className={`rozet ${SINIF[durum]}`}>{BELGE_DURUMU[durum]}</span>;
}

export function GuvenRozeti({ guven, uyari }: { guven: number | null; uyari: boolean }) {
  const metin = guven === null ? "okunamadı" : `%${Math.round(guven * 100)}`;
  return (
    <span className={`rozet ${uyari ? "uyari" : "soluk"}`} title="OCR güven skoru">
      {uyari ? "⚠ " : ""}OCR {metin}
    </span>
  );
}
