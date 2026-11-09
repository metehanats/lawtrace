import { expect, Page, test } from "@playwright/test";
import { girisVeListe, HESAP } from "./ortak";

// 2025/1487 test kurulumunda yalnızca kurallarla analiz edilir (araclar/e2e_sunucu.py): tarih ve tutar bulguları.

async function incelemeyiAc(page: Page, dugmeyle = true) {
  await page.getByRole("link", { name: "2025/1487" }).click();
  await page.getByRole("navigation", { name: "Dava bölümleri" }).getByRole("link", { name: /Bulgular/ }).click();
  if (dugmeyle) {
    await page.getByRole("button", { name: /İncelemeye başla|Kaynaklarıyla gözden geçir/ }).click();
  } else {
    // Stajyerde "İncelemeye başla" düğmesi yok; inceleme ekranı adresle açılır (salt okuma)
    await expect(page).toHaveURL(/sekme=bulgular/);
    await page.goto(page.url().replace("sekme=bulgular", "sekme=inceleme"));
  }
  await expect(page.getByRole("heading", { name: "Bulguları kaynağıyla incele" })).toBeVisible();
}

async function incelenmemis(page: Page): Promise<number> {
  const metin = await page.getByText(/\d+ incelenmemiş · \d+ bulgu/).textContent();
  return Number(metin!.match(/(\d+) incelenmemiş/)![1]);
}

test("avukat bulguyu kaynağında görür ve A ile onaylar; karar kalıcıdır", async ({ page }) => {
  await girisVeListe(page, HESAP.avukat);
  await incelemeyiAc(page);

  // Seçili bulgunun alıntısı kaynak sayfada işaretli
  await expect(page.locator("mark.kaynak")).toBeVisible();
  const once = await incelenmemis(page);
  expect(once).toBeGreaterThan(0);

  await page.keyboard.press("a");
  await expect.poll(() => incelenmemis(page)).toBe(once - 1);
  // Varsayılan liste yalnızca incelenmemişleri gösterir; onaylanan, "tümü"nde görünür
  await page.getByLabel("Gösterilecek bulgular").selectOption("hepsi");
  await expect(page.getByText("Onaylandı").first()).toBeVisible();

  await page.reload();
  await expect.poll(() => incelenmemis(page)).toBe(once - 1);
});

test("stajyer bulguları görür ama karar düğmeleri yoktur", async ({ page }) => {
  await girisVeListe(page, HESAP.stajyer);
  await incelemeyiAc(page, false);
  await expect(page.locator("mark.kaynak")).toBeVisible();
  await expect(page.getByRole("button", { name: /Onayla/ })).toHaveCount(0);
  await expect(page.getByText("Stajyer hesapları bulguları görebilir ama onaylayamaz ya da reddedemez.")).toBeVisible();
});
