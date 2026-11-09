"""Analizin uygulamaya bağlanması.

- buro.analiz_modeli: bu büroda analiz için kullanılacak model ("ollama:qwen3.5:4b" gibi).
  NULL ise analiz kapalıdır (varsayılan; KVKK karşılaştırma belgesindeki öneri).
- belge.ozel_nitelikli + nedeni + avukat onayı: sağlık, adli sicil gibi özel nitelikli veri
  içeren belgeler avukatın ayrıca onayı olmadan analize gönderilmez.
- isleme_gorevi.analiz_calistirmasi_id: 'analiz' görevinin hangi çalıştırmaya ait olduğu.
- denetim_kaydi.eylem: 'analiz' ve 'guncelleme' (ör. özel nitelik işaretinin elle değiştirilmesi) eklenir.

Geri alma: 'analiz' denetim kaydı varken eski eylem kısıtı kurulamaz ve geri alma hata verir.

Revision ID: 0005
Revises: 0004
"""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

ESKI_EYLEMLER = (
    "'goruntuleme', 'yukleme', 'silme', 'onay', 'reddetme', 'disa_aktarim', 'erisim_reddi', "
    "'giris', 'giris_basarisiz', 'cikis', 'olusturma', 'erisim_degisikligi'"
)
YENI_EYLEMLER = ESKI_EYLEMLER + ", 'analiz', 'guncelleme'"


def upgrade() -> None:
    op.execute("ALTER TABLE buro ADD COLUMN analiz_modeli TEXT")
    op.execute(
        "ALTER TABLE belge "
        "ADD COLUMN ozel_nitelikli BOOLEAN NOT NULL DEFAULT false, "
        "ADD COLUMN ozel_nitelik_nedeni TEXT, "
        "ADD COLUMN ozel_nitelik_onay_kullanici_id UUID REFERENCES kullanici(id), "
        "ADD COLUMN ozel_nitelik_onay_zamani TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE isleme_gorevi ADD COLUMN analiz_calistirmasi_id UUID "
        "REFERENCES analiz_calistirmasi(id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX idx_bulgu_analiz ON bulgu(analiz_calistirmasi_id)")
    op.execute("CREATE INDEX idx_alinti_belge ON kaynak_alinti(belge_id)")
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({YENI_EYLEMLER}))"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE denetim_kaydi DROP CONSTRAINT denetim_kaydi_eylem_check")
    op.execute(
        f"ALTER TABLE denetim_kaydi ADD CONSTRAINT denetim_kaydi_eylem_check CHECK (eylem IN ({ESKI_EYLEMLER}))"
    )
    op.execute("DROP INDEX idx_alinti_belge")
    op.execute("DROP INDEX idx_bulgu_analiz")
    op.execute("ALTER TABLE isleme_gorevi DROP COLUMN analiz_calistirmasi_id")
    op.execute(
        "ALTER TABLE belge DROP COLUMN ozel_nitelikli, DROP COLUMN ozel_nitelik_nedeni, "
        "DROP COLUMN ozel_nitelik_onay_kullanici_id, DROP COLUMN ozel_nitelik_onay_zamani"
    )
    op.execute("ALTER TABLE buro DROP COLUMN analiz_modeli")
