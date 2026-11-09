import path from "node:path";
import { defineConfig } from "@playwright/test";

// Arayüz (uçtan uca) testleri. Geliştirme sunucularına (3000/8000) ve geliştirme veritabanına dokunmaz:
// - API 8100'de, her çalıştırmada sıfırdan kurulan "lawtrace_e2e" veritabanıyla (araclar/e2e_sunucu.py),
// - arayüz 3100'de, ayrı derleme klasörüyle (.next-e2e) üretim kipinde çalışır.
// Tarayıcı indirilmez; bilgisayardaki Microsoft Edge kullanılır.
//
//   npm run e2e

const API = "http://127.0.0.1:8100";
const ARAYUZ = "http://localhost:3100";
const KOK = path.resolve(__dirname, "..");
// Komutlar Windows'ta cmd.exe ile çalışır; göreli "../" yerine tam yol ve tırnak
const python = `"${path.join(KOK, ".venv", "Scripts", "python.exe")}"`;

export default defineConfig({
  testDir: "./e2e",
  // Testler aynı veritabanını paylaşır; sıra ile çalışır, her test kendi benzersiz kayıtlarını açar
  workers: 1,
  fullyParallel: false,
  timeout: 30_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: ARAYUZ,
    channel: "msedge",
    locale: "tr-TR",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: [
    {
      command: `${python} "${path.join(KOK, "araclar", "e2e_sunucu.py")}" --port 8100`,
      url: `${API}/oturum/ben`,          // 401 de "hazır" sayılır
      timeout: 300_000,
      reuseExistingServer: false,
      stdout: "ignore",
    },
    {
      command: "npx next build && npx next start --port 3100",
      url: ARAYUZ + "/giris",
      timeout: 300_000,
      reuseExistingServer: false,
      env: { NEXT_DIST_DIR: ".next-e2e", API_ADRESI: API },
      stdout: "ignore",
    },
  ],
});
