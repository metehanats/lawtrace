"""Müvekkil ve dava dosyası oluşturma, dosya erişimi yönetimi.

- muvekkil.kimlik_no_ozet: kimlik/vergi numarasının anahtarlı özeti (HMAC-SHA256).
  Şifreli numara çözülmeden aynı büroda mükerrer müvekkil kaydını engeller.
- muvekkil.olusturan_kullanici_id
- denetim_kaydi.eylem: 'olusturma', 'erisim_degisikligi' eklenir.

Geri alma: bu eylemlerle denetim kaydı varken eski kısıt kurulamaz ve geri alma
hata verir; denetim kayıtları silinmez.

Revision ID: 0004
Revises: 0003
"""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

ESKI_EYLEMLER = (
    "'goruntuleme', 'yukleme', 'silme', 'onay', 'reddetme', 'disa_aktarim', 'erisim_reddi', "
    "'giris', 'giris_basarisiz', 'cikis'"
)
YENI_EYLEMLER = ESKI_EYLEMLER + ", 'olusturma', 'erisim_degisikligi'"


def upgrade() -> None:
    op.execute(
        "ALTER TABLE muvekkil "
        "ADD COLUMN kimlik_no_ozet CHAR(64), "
        "ADD COLUMN olusturan_kullanici_id UUID REFERENCES kullanici(id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX idx_muvekkil_kimlik_ozet ON muvekkil (buro_id, kimlik_no_ozet) "
        "WHERE kimlik_no_ozet IS NOT NULL"
    )
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({YENI_EYLEMLER}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({ESKI_EYLEMLER}))"
    )
    op.execute("DROP INDEX idx_muvekkil_kimlik_ozet")
    op.execute("ALTER TABLE muvekkil DROP COLUMN kimlik_no_ozet, DROP COLUMN olusturan_kullanici_id")
