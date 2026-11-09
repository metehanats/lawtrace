"""Yönetici ekranları: geçici parola ile açılan hesaplar.

- kullanici.parola_degismeli: yönetici hesap açtığında ya da parolayı sıfırladığında tek
  kullanımlık geçici parola verilir ve bu alan true olur. Kullanıcı parolasını değiştirene kadar
  oturumu yalnızca parola değiştirme ve çıkış için kullanabilir.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE kullanici ADD COLUMN parola_degismeli BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE kullanici DROP COLUMN parola_degismeli")
