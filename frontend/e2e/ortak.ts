import { readFileSync } from "node:fs";
import path from "node:path";
import { expect, Page } from "@playwright/test";

// Demo hesapları ve parolası tek yerde, sentetik veri betiğinde durur; burada tekrar yazılmaz.
const demoBetigi = readFileSync(path.join(__dirname, "..", "..", "araclar", "demo_veri.py"), "utf-8");
export const DEMO_PAROLA = demoBetigi.match(/^DEMO_PAROLA = "([^"]+)"/m)![1];

export const HESAP = {
  yonetici: "yonetici@demo.test",
  avukat: "avukat@demo.test",
  stajyer: "stajyer@demo.test",
} as const;

/** Her çalıştırmada farklı, kısa bir ek: testler aynı veritabanında birbirinin kaydına çarpmasın. */
export const ek = () => Math.random().toString(36).slice(2, 7);

export async function girisYap(page: Page, ePosta: string, parola = DEMO_PAROLA) {
  await page.goto("/giris");
  await page.getByLabel("E-posta").fill(ePosta);
  await page.getByLabel("Parola").fill(parola);
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

/** Giriş yapar ve dava listesinin açılmasını bekler. */
export async function girisVeListe(page: Page, ePosta: string) {
  await girisYap(page, ePosta);
  await expect(page.getByRole("heading", { name: "Dava dosyaları" })).toBeVisible();
}
