"""Kimlik doğrulama: kullanıcı parolası, giriş kilidi ve oturumlar.

- kullanici: parola_ozet (Argon2id), basarisiz_giris, kilit_bitis, parola_degisim
- oturum: tarayıcı çerezindeki rastgele belirtecin yalnızca SHA-256 özeti tutulur;
  veritabanı sızsa bile oturumlar ele geçirilemez.
- denetim_kaydi.eylem: 'giris', 'giris_basarisiz', 'cikis' eklenir.

Geri alma: giriş kayıtları varken eski eylem kısıtı yeniden kurulamaz ve geri alma
hata verir; denetim kayıtları silinmez.

Revision ID: 0003
Revises: 0002
"""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

ESKI_EYLEMLER = "'goruntuleme', 'yukleme', 'silme', 'onay', 'reddetme', 'disa_aktarim', 'erisim_reddi'"
YENI_EYLEMLER = ESKI_EYLEMLER + ", 'giris', 'giris_basarisiz', 'cikis'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE kullanici "
        "ADD COLUMN parola_ozet TEXT, "
        "ADD COLUMN basarisiz_giris INTEGER NOT NULL DEFAULT 0, "
        "ADD COLUMN kilit_bitis TIMESTAMPTZ, "
        "ADD COLUMN parola_degisim TIMESTAMPTZ"
    )
    # E-posta büyük/küçük harf duyarsız tekil olmalı; girişte lower() ile aranır
    op.execute("CREATE UNIQUE INDEX idx_kullanici_e_posta_kucuk ON kullanici (lower(e_posta))")
    op.execute(
        """
        CREATE TABLE oturum (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kullanici_id    UUID NOT NULL REFERENCES kullanici(id) ON DELETE CASCADE,
            belirtec_ozet   CHAR(64) NOT NULL UNIQUE,
            olusturma       TIMESTAMPTZ NOT NULL DEFAULT now(),
            son_kullanim    TIMESTAMPTZ NOT NULL DEFAULT now(),
            bitis           TIMESTAMPTZ NOT NULL,
            iptal           TIMESTAMPTZ,
            ip_adresi       INET,
            kullanici_araci TEXT
        )
        """
    )
    op.execute("CREATE INDEX idx_oturum_kullanici ON oturum (kullanici_id)")
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({YENI_EYLEMLER}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({ESKI_EYLEMLER}))"
    )
    op.execute("DROP TABLE oturum")
    op.execute("DROP INDEX idx_kullanici_e_posta_kucuk")
    op.execute(
        "ALTER TABLE kullanici DROP COLUMN parola_ozet, DROP COLUMN basarisiz_giris, "
        "DROP COLUMN kilit_bitis, DROP COLUMN parola_degisim"
    )
