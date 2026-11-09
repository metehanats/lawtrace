// Uygulamadaki simgelerin tek kaynağı (Tabler Icons, MIT; kullanıcının 2026-10-31'de onayladığı seçim).
// Bir simgeyi değiştirmek için yalnızca bu dosya düzenlenir. Simgeler metnin rengini alır (currentColor).

import {
  IconArrowsDiff, IconBackpack, IconBriefcase, IconCalendarEvent, IconCheck, IconCrown, IconFiles, IconKey,
  IconLayoutDashboard, IconListSearch, IconLockPassword, IconMoon, IconPower, IconScale, IconShieldLock, IconSun,
  IconTie, IconUpload, IconUsers, IconX, IconZoomScan,
} from "@tabler/icons-react";
import type { ComponentType } from "react";
import { Kullanici, ROL } from "@/lib/api";

type SimgeBileseni = ComponentType<{ size?: number; stroke?: number; className?: string; "aria-hidden"?: boolean }>;

export const SIMGE = {
  marka: IconScale,
  davalar: IconBriefcase,
  muvekkiller: IconUsers,
  yonetim: IconShieldLock,
  ozet: IconLayoutDashboard,
  belgeler: IconFiles,
  bulgular: IconListSearch,
  celiskiler: IconArrowsDiff,
  zaman: IconCalendarEvent,
  iddia: IconScale,
  erisim: IconKey,
  onayla: IconCheck,
  reddet: IconX,
  analiz: IconZoomScan,
  yukle: IconUpload,
  parola: IconLockPassword,
  cikis: IconPower,
  acik: IconSun,
  koyu: IconMoon,
  // Roller (kullanıcının 2026-11-01'de onayladığı seçim)
  stajyer: IconBackpack,
  avukat: IconTie,
  yonetici: IconCrown,
} satisfies Record<string, SimgeBileseni>;

export type SimgeAdi = keyof typeof SIMGE;

/** Rol adı simgesiyle (ör. kravat + "Avukat"). */
export function Rol({ rol }: { rol: Kullanici["rol"] }) {
  return <span className="rol"><Simge ad={rol} boyut={15} />{ROL[rol]}</span>;
}

/** Metnin yanında kullanılan simge; ekran okuyucudan gizlenir (anlamı yanındaki metin taşır). */
export function Simge({ ad, boyut = 18 }: { ad: SimgeAdi; boyut?: number }) {
  const Bilesen = SIMGE[ad];
  return <Bilesen size={boyut} stroke={1.75} className="simge" aria-hidden />;
}
