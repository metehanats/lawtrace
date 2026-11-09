import type { NextConfig } from "next";

// Tarayıcı yalnızca bu sunucuyla konuşur; /api/* istekleri FastAPI'ye iletilir.
// Böylece oturum çerezi aynı kaynakta kalır (SameSite=Lax ile sorunsuz) ve CORS gerekmez.
const API_ADRESI = process.env.API_ADRESI ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:yol*", destination: `${API_ADRESI}/:yol*` }];
  },
  async headers() {
    return [
      {
        source: "/:yol*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "same-origin" },
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
  poweredByHeader: false,
  // Arayüz testleri ayrı bir derleme klasörü kullanır; çalışan geliştirme sunucusunun .next'ine dokunmaz
  distDir: process.env.NEXT_DIST_DIR || ".next",
};

export default nextConfig;
