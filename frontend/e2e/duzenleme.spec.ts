import { expect, test } from "@playwright/test";
import { ek, girisVeListe, HESAP } from "./ortak";

// Basit, geçerli bir PDF (metin katmanlı tek sayfa). İşçi bu testlerde çalışmaz; belge "yüklendi" durumunda kalır.
function pdf(metin: string): Buffer {
  const nesneler = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
  ];
  const akis = `BT /F1 12 Tf 72 770 Td (${metin}) Tj ET`;
  nesneler.push(`<< /Length ${akis.length} >>\nstream\n${akis}\nendstream`);
  nesneler.push("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>");
  let govde = "%PDF-1.4\n";
  const konumlar: number[] = [];
  nesneler.forEach((n, i) => {
    konumlar.push(govde.length);
    govde += `${i + 1} 0 obj\n${n}\nendobj\n`;
  });
  const xref = govde.length;
  govde += `xref\n0 ${nesneler.length + 1}\n0000000000 65535 f \n`;
  govde += konumlar.map((k) => `${String(k).padStart(10, "0")} 00000 n \n`).join("");
  govde += `trailer\n<< /Size ${nesneler.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(govde, "latin1");
}

test("müvekkil eklenir, düzenlenir; boş bırakılan alan silinir", async ({ page }) => {
  const ad = `Sentetik Müvekkil ${ek()}`;
  await girisVeListe(page, HESAP.avukat);
  await page.goto("/muvekkiller/yeni");
  await page.getByLabel("Ad soyad").fill(ad);
  await page.getByLabel("Telefon").fill("0555 000 00 00");
  await page.getByLabel("Adres").fill("Sentetik Mah. No: 1");
  await page.getByRole("button", { name: "Kaydet" }).click();
  await expect(page.getByRole("heading", { name: ad })).toBeVisible();

  await page.getByRole("link", { name: "Düzenle" }).click();
  await expect(page.getByLabel("Ad soyad")).toHaveValue(ad);
  await page.getByLabel("Ad soyad").fill(`${ad} (düzeltildi)`);
  await page.getByLabel("Adres").fill("");
  await page.getByRole("button", { name: "Kaydet" }).click();

  await expect(page.getByRole("heading", { name: `${ad} (düzeltildi)` })).toBeVisible();
  await expect(page.getByText("0555 000 00 00")).toBeVisible();
  await expect(page.getByText("Sentetik Mah. No: 1")).toHaveCount(0);
});

test("dava açılır, belge yüklenir; kapatılınca salt okunur olur, yeniden açılır", async ({ page }) => {
  const no = `2026/E2E-${ek()}`;
  await girisVeListe(page, HESAP.avukat);
  await page.getByRole("link", { name: "Yeni dava dosyası" }).click();
  await page.getByLabel("Müvekkil").selectOption({ label: "Ayşe Yılmaz" });
  await page.getByLabel("Dosya no").fill(no);
  await page.getByLabel("Başlık").fill("Sentetik arayüz testi davası");
  await page.getByRole("button", { name: "Dosyayı aç" }).click();
  await expect(page.getByRole("heading", { name: "Sentetik arayüz testi davası" })).toBeVisible();

  // Belge yükle
  await page.getByRole("link", { name: "Belgeler" }).click();
  await page.getByLabel("Yüklenecek belgeler").setInputFiles({
    name: "sentetik-dilekce.pdf", mimeType: "application/pdf", buffer: pdf("Sentetik dilekce"),
  });
  await expect(page.getByRole("cell", { name: /sentetik-dilekce\.pdf/ })).toBeVisible();

  // Kapat
  await page.getByRole("link", { name: "Düzenle" }).click();
  await page.getByRole("radio", { name: "Kapalı" }).check();
  await page.getByRole("button", { name: "Kaydet" }).click();
  await expect(page.getByText(/Bu dosya kapalı ve salt okunur/)).toBeVisible();
  await page.getByRole("link", { name: "Belgeler" }).click();
  await expect(page.getByLabel("Yüklenecek belgeler")).toHaveCount(0);

  // Kapalıyken bilgiler kilitli; yeniden aç
  await page.getByRole("link", { name: "Yeniden aç / düzenle" }).click();
  await expect(page.getByLabel("Başlık")).toBeDisabled();
  await page.getByRole("radio", { name: "Açık" }).check();
  await expect(page.getByLabel("Başlık")).toBeEnabled();
  await page.getByRole("button", { name: "Kaydet" }).click();
  await expect(page.getByText(/Bu dosya kapalı/)).toHaveCount(0);
  await page.getByRole("link", { name: "Belgeler" }).click();
  await expect(page.getByLabel("Yüklenecek belgeler")).toHaveCount(1);
});
