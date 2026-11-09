"""Büro ve kullanıcı yönetimi için komut satırı aracı.

Kullanıcı yönetimi arayüzü yazılana kadar hesaplar bu araçla açılır. Parola komut
satırı argümanı olarak verilmez (komut geçmişine yazılırdı); ekranda görünmeden sorulur.

    python -m app.kimlik.yonetim buro-ekle --ad "Örnek Hukuk Bürosu"
    python -m app.kimlik.yonetim kullanici-ekle --buro-id <id> --ad-soyad "Av. Ad Soyad" --e-posta ad@ornek.test --rol avukat
    python -m app.kimlik.yonetim parola-belirle --e-posta ad@ornek.test
    python -m app.kimlik.yonetim kilit-ac --e-posta ad@ornek.test
    python -m app.kimlik.yonetim pasiflestir --e-posta ad@ornek.test
    python -m app.kimlik.yonetim listele
    python -m app.kimlik.yonetim analiz-ayarla --buro-id <id> --model ollama:qwen3.5:4b
    python -m app.kimlik.yonetim analiz-ayarla --buro-id <id> --kapat
"""

import argparse
import getpass
import sys

from sqlalchemy import Connection, text

from app.db import engine
from app.kimlik import oturum, parola as parola_mod


class YonetimHatasi(Exception):
    pass


def buro_ekle(conn: Connection, ad: str) -> str:
    return str(conn.execute(text("INSERT INTO buro (ad) VALUES (:a) RETURNING id"), {"a": ad}).scalar_one())


def kullanici_ekle(conn: Connection, *, buro_id: str, ad_soyad: str, e_posta: str, rol: str,
                   parola: str | None) -> str:
    if parola is not None:
        sorun = parola_mod.parola_sorunu(parola, e_posta)
        if sorun:
            raise YonetimHatasi(sorun)
    return str(conn.execute(
        text(
            "INSERT INTO kullanici (buro_id, ad_soyad, e_posta, rol, parola_ozet, parola_degisim) "
            "VALUES (:b, :a, lower(:e), :r, CAST(:p AS TEXT), "
            "CASE WHEN CAST(:p AS TEXT) IS NULL THEN NULL ELSE now() END) RETURNING id"
        ),
        {"b": buro_id, "a": ad_soyad, "e": e_posta.strip(), "r": rol,
         "p": parola_mod.ozetle(parola) if parola is not None else None},
    ).scalar_one())


def _kullanici_bul(conn: Connection, e_posta: str):
    kullanici = conn.execute(
        text("SELECT id, e_posta FROM kullanici WHERE lower(e_posta) = lower(:e)"), {"e": e_posta.strip()}
    ).one_or_none()
    if kullanici is None:
        raise YonetimHatasi(f"Kullanıcı bulunamadı: {e_posta}")
    return kullanici


def parola_belirle(conn: Connection, e_posta: str, parola: str) -> int:
    """Parolayı değiştirir, kilidi açar ve kullanıcının açık oturumlarını kapatır."""
    kullanici = _kullanici_bul(conn, e_posta)
    sorun = parola_mod.parola_sorunu(parola, kullanici.e_posta)
    if sorun:
        raise YonetimHatasi(sorun)
    conn.execute(
        text(
            "UPDATE kullanici SET parola_ozet = :p, parola_degisim = now(), parola_degismeli = false, "
            "basarisiz_giris = 0, kilit_bitis = NULL WHERE id = :k"
        ),
        {"p": parola_mod.ozetle(parola), "k": kullanici.id},
    )
    return oturum.tum_oturumlari_kapat(conn, kullanici.id)


def kilit_ac(conn: Connection, e_posta: str) -> None:
    kullanici = _kullanici_bul(conn, e_posta)
    conn.execute(text("UPDATE kullanici SET basarisiz_giris = 0, kilit_bitis = NULL WHERE id = :k"),
                 {"k": kullanici.id})


def pasiflestir(conn: Connection, e_posta: str) -> int:
    kullanici = _kullanici_bul(conn, e_posta)
    conn.execute(text("UPDATE kullanici SET aktif = false WHERE id = :k"), {"k": kullanici.id})
    return oturum.tum_oturumlari_kapat(conn, kullanici.id)


def analiz_ayarla(conn: Connection, buro_id: str, model: str | None) -> None:
    """Büroda analizi açar (model tanımıyla, ör. "ollama:qwen3.5:4b") ya da kapatır (None)."""
    if model is not None and not model.startswith("ollama:"):
        # Bulut sağlayıcılar KVKK değerlendirmesi tamamlanmadan eklenmeyecek (docs/devir-notu.md)
        raise YonetimHatasi("Şimdilik yalnızca yerel Ollama modelleri desteklenir (ör. ollama:qwen3.5:4b).")
    guncellenen = conn.execute(
        text("UPDATE buro SET analiz_modeli = :m WHERE id = :b"), {"b": buro_id, "m": model}
    ).rowcount
    if not guncellenen:
        raise YonetimHatasi(f"Büro bulunamadı: {buro_id}")


def _parola_sor() -> str:
    birinci = getpass.getpass("Parola: ")
    if getpass.getpass("Parola (tekrar): ") != birinci:
        raise YonetimHatasi("Parolalar aynı değil.")
    return birinci


def main(argv: list[str] | None = None) -> int:
    ayristirici = argparse.ArgumentParser(description="Büro ve kullanıcı yönetimi")
    alt = ayristirici.add_subparsers(dest="komut", required=True)
    b = alt.add_parser("buro-ekle")
    b.add_argument("--ad", required=True)
    k = alt.add_parser("kullanici-ekle")
    k.add_argument("--buro-id", required=True)
    k.add_argument("--ad-soyad", required=True)
    k.add_argument("--e-posta", required=True)
    k.add_argument("--rol", required=True, choices=["yonetici", "avukat", "stajyer"])
    k.add_argument("--parolasiz", action="store_true", help="Parola sonra parola-belirle ile verilecek")
    for ad in ("parola-belirle", "kilit-ac", "pasiflestir"):
        alt.add_parser(ad).add_argument("--e-posta", required=True)
    alt.add_parser("listele")
    a = alt.add_parser("analiz-ayarla", help="Büroda analizi aç (--model) ya da kapat (--kapat)")
    a.add_argument("--buro-id", required=True)
    g = a.add_mutually_exclusive_group(required=True)
    g.add_argument("--model", help='ör. "ollama:qwen3.5:4b"')
    g.add_argument("--kapat", action="store_true")
    s = ayristirici.parse_args(argv)

    try:
        if s.komut == "buro-ekle":
            with engine().begin() as conn:
                print(f"Büro eklendi: {buro_ekle(conn, s.ad)}")
        elif s.komut == "kullanici-ekle":
            parola = None if s.parolasiz else _parola_sor()
            with engine().begin() as conn:
                kimlik = kullanici_ekle(conn, buro_id=s.buro_id, ad_soyad=s.ad_soyad, e_posta=s.e_posta,
                                        rol=s.rol, parola=parola)
            print(f"Kullanıcı eklendi: {kimlik}")
        elif s.komut == "parola-belirle":
            parola = _parola_sor()
            with engine().begin() as conn:
                kapanan = parola_belirle(conn, s.e_posta, parola)
            print(f"Parola güncellendi; {kapanan} açık oturum kapatıldı.")
        elif s.komut == "kilit-ac":
            with engine().begin() as conn:
                kilit_ac(conn, s.e_posta)
            print("Kilit açıldı.")
        elif s.komut == "pasiflestir":
            with engine().begin() as conn:
                kapanan = pasiflestir(conn, s.e_posta)
            print(f"Hesap pasifleştirildi; {kapanan} açık oturum kapatıldı.")
        elif s.komut == "listele":
            with engine().connect() as conn:
                burolar = conn.execute(text("SELECT id, ad, analiz_modeli FROM buro ORDER BY ad")).all()
                satirlar = conn.execute(text(
                    "SELECT b.ad AS buro, k.e_posta, k.rol, k.aktif, k.parola_ozet IS NOT NULL AS parola, "
                    "k.kilit_bitis > now() AS kilitli, k.son_giris "
                    "FROM kullanici k JOIN buro b ON b.id = k.buro_id ORDER BY b.ad, k.e_posta"
                )).all()
            for b in burolar:
                print(f"Büro: {b.ad} | kimlik={b.id} | analiz={b.analiz_modeli or 'kapalı'}")
            for r in satirlar:
                print(f"{r.buro} | {r.e_posta} | {r.rol} | aktif={r.aktif} parola={r.parola} "
                      f"kilitli={bool(r.kilitli)} son_giris={r.son_giris}")
        elif s.komut == "analiz-ayarla":
            with engine().begin() as conn:
                analiz_ayarla(conn, s.buro_id, None if s.kapat else s.model)
            print("Analiz kapatıldı." if s.kapat else f"Analiz açıldı: {s.model}")
    except YonetimHatasi as hata:
        print(f"Hata: {hata}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
