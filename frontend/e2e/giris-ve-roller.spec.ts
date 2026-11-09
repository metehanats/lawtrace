import { expect, test } from "@playwright/test";
import { girisVeListe, girisYap, HESAP } from "./ortak";

test("yanlış parola hata verir, doğru parolayla dava listesi açılır", async ({ page }) => {
  await girisYap(page, HESAP.avukat, "yanlis-parola-123");
  await expect(page.getByRole("alert")).toBeVisible();
  await expect(page).toHaveURL(/\/giris/);

  await girisVeListe(page, HESAP.avukat);
  await expect(page).toHaveTitle("LawTrace");
  await expect(page.locator(".marka-ad")).toHaveText("LawTrace");
  await expect(page.getByRole("link", { name: "2025/1487" })).toBeVisible();
  await expect(page.getByRole("link", { name: "2026/0312" })).toBeVisible();
});

test("oturum yoksa korumalı sayfa girişe yönlendirir ve sonra geri döner", async ({ page }) => {
  await page.goto("/muvekkiller");
  await expect(page).toHaveURL(/\/giris\?donus=%2Fmuvekkiller/);
  await page.getByLabel("E-posta").fill(HESAP.avukat);
  await page.getByLabel("Parola").fill((await import("./ortak")).DEMO_PAROLA);
  await page.getByRole("button", { name: "Giriş yap" }).click();
  await expect(page.getByRole("heading", { name: "Müvekkiller" })).toBeVisible();
});

test("stajyer yalnızca erişimi olan dosyayı görür, oluşturma ve yönetim düğmeleri yoktur", async ({ page }) => {
  await girisVeListe(page, HESAP.stajyer);
  await expect(page.getByRole("link", { name: "2025/1487" })).toBeVisible();
  await expect(page.getByRole("link", { name: "2026/0312" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Yeni dava dosyası" })).toHaveCount(0);
  await expect(page.getByRole("link", { name: "Yönetim" })).toHaveCount(0);

  // Yönetim sayfasına adresle gidilse de açılmaz
  await page.goto("/yonetim");
  await expect(page.getByText("Bu sayfa yalnızca büro yöneticisine açıktır.")).toBeVisible();
  // Dosyada düzenleme düğmesi yok
  await page.goto("/davalar");
  await page.getByRole("link", { name: "2025/1487" }).click();
  await expect(page.getByRole("link", { name: "Erişim" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Düzenle" })).toHaveCount(0);
});

test("çıkış oturumu kapatır", async ({ page }) => {
  await girisVeListe(page, HESAP.avukat);
  await page.getByRole("button", { name: "Çıkış" }).click();
  await expect(page).toHaveURL(/\/giris/);
  await page.goto("/davalar");
  await expect(page).toHaveURL(/\/giris/);
});

test("dava listesinde arama süzer", async ({ page }) => {
  await girisVeListe(page, HESAP.avukat);
  await page.getByLabel("Dava dosyalarında ara").fill("lojistik");
  await expect(page.getByRole("link", { name: "2026/0312" })).toBeVisible();
  await expect(page.getByRole("link", { name: "2025/1487" })).toHaveCount(0);
});
