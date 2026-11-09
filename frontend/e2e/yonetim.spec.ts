import { expect, test } from "@playwright/test";
import { ek, girisVeListe, girisYap, HESAP } from "./ortak";

test("yeni hesap geçici parolayla açılır, ilk girişte parola belirlemek zorunludur", async ({ page, browser }) => {
  const ePosta = `yeni.${ek()}@demo.test`;
  await girisVeListe(page, HESAP.yonetici);
  await page.getByRole("link", { name: "Yönetim" }).click();
  await page.getByLabel("Ad soyad").fill("Av. Sentetik Yeni");
  await page.locator("#yeni_e_posta").fill(ePosta);
  await page.getByLabel("Rol", { exact: true }).selectOption("avukat");
  await page.getByRole("button", { name: "Hesabı aç" }).click();
  // Parola kutusu sayfanın üstünde değil, yeni kullanıcının satırının altında ve görünür alanda açılır
  const kutu = page.locator("tr.gecici-satir");
  await expect(kutu).toContainText(ePosta);
  await expect(kutu).toBeInViewport();
  await expect(page.getByRole("row").filter({ hasText: ePosta }).first()).toBeVisible();
  const gecici = (await kutu.locator("code.gecici-parola").textContent())!.trim();
  expect(gecici.length).toBeGreaterThan(8);

  // Yeni kullanıcı ayrı tarayıcı bağlamında girer
  const baglam = await browser.newContext();
  const yeni = await baglam.newPage();
  await girisYap(yeni, ePosta, gecici);
  await expect(yeni.getByRole("heading", { name: "Parolanızı belirleyin" })).toBeVisible();
  // Başka sayfaya gitse de önce parola istenir
  await yeni.goto("/muvekkiller");
  await expect(yeni.getByRole("heading", { name: "Parolanızı belirleyin" })).toBeVisible();
  const parola = `Sentetik-E2E-${ek()}-Parola-71`;
  await yeni.getByLabel("Geçici parola").fill(gecici);
  await yeni.getByLabel("Yeni parola", { exact: true }).fill(parola);
  await yeni.getByLabel("Yeni parola (tekrar)").fill(parola);
  await yeni.getByRole("button", { name: "Parolayı kaydet" }).click();
  await expect(yeni.getByRole("heading", { name: "Müvekkiller" })).toBeVisible();
  await baglam.close();

  // Var olan kullanıcıya yeniden geçici parola: kutu yine o kişinin satırının altında açılır
  await page.reload();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("row").filter({ hasText: ePosta }).getByRole("button", { name: "Geçici parola" }).click();
  await expect(page.locator("tr.gecici-satir")).toContainText(ePosta);
  await expect(page.locator("tr.gecici-satir")).toBeInViewport();
  await expect(page.locator("tr.gecici-satir code.gecici-parola")).not.toHaveText(gecici);
});

test("yönetici büro adını ve kullanıcının adını değiştirir", async ({ page }) => {
  await girisVeListe(page, HESAP.yonetici);
  await page.goto("/yonetim");

  await page.getByRole("button", { name: "Adı değiştir" }).click();
  await page.getByLabel("Büro adı").fill("Demo Hukuk Bürosu (test)");
  await page.getByRole("button", { name: "Kaydet" }).click();
  await expect(page.getByText("Büro adı değiştirildi.")).toBeVisible();
  await expect(page.getByText("Demo Hukuk Bürosu (test) · kullanıcılar ve büro ayarları")).toBeVisible();

  const satir = page.getByRole("row").filter({ hasText: "stajyer@demo.test" });
  await satir.getByRole("button", { name: "Düzenle" }).click();
  await page.getByRole("row").filter({ has: page.getByLabel("Ad soyad", { exact: true }) })
    .getByLabel("Ad soyad", { exact: true }).fill("Stj. Av. Kerem Yeniad");
  await page.getByRole("button", { name: "Kaydet" }).first().click();
  await expect(page.getByText("Stj. Av. Kerem Yeniad: bilgiler kaydedildi.")).toBeVisible();

  // Değişiklikler denetim kaydında
  await page.getByRole("link", { name: "Denetim kaydı" }).click();
  await expect(page.getByText("Güncelleme").first()).toBeVisible();
});

test("tema anahtarı seçimi sayfa yenilense de korunur", async ({ page }) => {
  await girisVeListe(page, HESAP.avukat);
  const anahtar = page.getByRole("switch", { name: "Koyu tema" });
  const once = await page.locator("html").getAttribute("data-tema");
  await anahtar.click();
  const sonra = once === "koyu" ? "acik" : "koyu";
  await expect(page.locator("html")).toHaveAttribute("data-tema", sonra);
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-tema", sonra);
});
