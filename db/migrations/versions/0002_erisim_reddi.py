"""Denetim kaydına reddedilen erişim denemeleri.

- eylem listesine 'erisim_reddi' eklenir.
- ayrinti (JSONB) alanı eklenir; reddin nedeni ve istenen eylem burada tutulur,
  ör. {"neden": "yetki_yok", "istenen_eylem": "goruntuleme"}.
- Reddedilen denemeleri kullanıcıya ve zamana göre sorgulamak için kısmi indeks.

Geri alma: erisim_reddi kayıtları varken eski kısıt yeniden kurulamaz ve geri alma
hata verir. Bu bilinçlidir; denetim kayıtları geri alma sırasında silinmez.

Revision ID: 0002
Revises: 0001
"""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

ESKI_EYLEMLER = "'goruntuleme', 'yukleme', 'silme', 'onay', 'reddetme', 'disa_aktarim'"
YENI_EYLEMLER = ESKI_EYLEMLER + ", 'erisim_reddi'"


def upgrade() -> None:
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({YENI_EYLEMLER}))"
    )
    op.execute("ALTER TABLE denetim_kaydi ADD COLUMN ayrinti JSONB")
    op.execute(
        "CREATE INDEX idx_denetim_reddi ON denetim_kaydi (buro_id, kullanici_id, zaman) "
        "WHERE eylem = 'erisim_reddi'"
    )


def downgrade() -> None:
    op.execute("DROP INDEX idx_denetim_reddi")
    op.execute("ALTER TABLE denetim_kaydi DROP COLUMN ayrinti")
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({ESKI_EYLEMLER}))"
    )
