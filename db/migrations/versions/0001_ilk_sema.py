"""İlk şema: büro, kullanıcı, dava dosyası, belge, bulgu, kaynak, delil ve denetim tabloları.

Bu migrasyon, yanındaki 0001_ilk_sema.sql dosyasını çalıştırır. O dosya ilk şemanın
dondurulmuş kopyasıdır ve değiştirilmez. (2026-10-29'a kadar bu migrasyon doğrudan
db/schema.sql dosyasını okuyordu; schema.sql değiştikçe 0001 de sessizce değişirdi.
Uygulanan SQL aynı kaldı, yalnızca okunduğu dosya değişti.)

db/schema.sql, tüm migrasyonlar uygulandıktan sonraki güncel şemayı gösteren
başvuru belgesidir; şema değişiklikleri yeni migrasyonlarla yapılır.

Revision ID: 0001
Revises:
"""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMA_PATH = Path(__file__).with_suffix(".sql")

# Bağımlılık sırasının tersine (önce bağımlı tablolar) düşürülür.
TABLES = [
    "denetim_kaydi",
    "delil_baglantisi",
    "iddia",
    "olay",
    "uyusmazlik",
    "bulgu_inceleme",
    "kaynak_alinti",
    "bulgu",
    "analiz_calistirmasi",
    "isleme_gorevi",
    "belge_sayfa",
    "belge",
    "dosya_erisim",
    "dava_dosyasi",
    "muvekkil",
    "kullanici",
    "buro",
]


def upgrade() -> None:
    op.execute(SCHEMA_PATH.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
