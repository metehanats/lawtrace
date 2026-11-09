import type { Metadata } from "next";
import Script from "next/script";
import "./globals.css";

export const metadata: Metadata = {
  title: "LawTrace",
  description: "Her bulgunun izi belgesinde: dava dosyalarını kaynaklarıyla inceleme",
  robots: { index: false, follow: false },
};

// Tema, sayfa çizilmeden önce uygulanır; yoksa koyu temada açılışta bir an beyaz parlar.
// Seçim tarayıcıda "tema" anahtarında: "sistem" (varsayılan, Windows ayarına uyar), "acik" ya da "koyu".
const TEMA_BETIGI = `(function(){try{var t=localStorage.getItem("tema")||"sistem";var k=t==="koyu"||(t==="sistem"&&matchMedia("(prefers-color-scheme: dark)").matches);document.documentElement.dataset.tema=k?"koyu":"acik";}catch(e){}})();`;

export default function KokYerlesim({ children }: { children: React.ReactNode }) {
  return (
    // data-tema betik tarafından istemcide konur; sunucu çıktısıyla farkı beklenen bir farktır
    <html lang="tr" suppressHydrationWarning>
      <body>
        {/* beforeInteractive: Next.js betiği sayfa etkileşime geçmeden, <head> içinde çalıştırır */}
        <Script id="tema" strategy="beforeInteractive">{TEMA_BETIGI}</Script>
        {children}
      </body>
    </html>
  );
}
