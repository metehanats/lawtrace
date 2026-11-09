-- =========================================================
-- Hukuk Dava Analizi MVP - PostgreSQL şeması (ilk sürüm)
-- Gereksinim: PostgreSQL 15+ (gen_random_uuid() yerleşik)
-- =========================================================

-- 1. KİRACI VE KULLANICILAR -------------------------------

CREATE TABLE buro (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ad              TEXT NOT NULL,
    vergi_no        TEXT UNIQUE,
    durum           TEXT NOT NULL DEFAULT 'aktif'
                    CHECK (durum IN ('aktif', 'askida', 'kapali')),
    olusturma       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE kullanici (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buro_id         UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    ad_soyad        TEXT NOT NULL,
    e_posta         TEXT NOT NULL UNIQUE,
    rol             TEXT NOT NULL
                    CHECK (rol IN ('yonetici', 'avukat', 'stajyer')),
    aktif           BOOLEAN NOT NULL DEFAULT true,
    son_giris       TIMESTAMPTZ,
    olusturma       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_kullanici_buro ON kullanici(buro_id);

-- 2. MÜVEKKİL VE DAVA DOSYASI -----------------------------

CREATE TABLE muvekkil (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buro_id                 UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    tur                     TEXT NOT NULL CHECK (tur IN ('gercek_kisi', 'tuzel_kisi')),
    ad_unvan                TEXT NOT NULL,
    -- Hassas alanlar uygulama katmanında şifrelenmiş olarak saklanır
    kimlik_no_sifreli       BYTEA,
    iletisim_sifreli        BYTEA,
    olusturma               TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_muvekkil_buro ON muvekkil(buro_id);

CREATE TABLE dava_dosyasi (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buro_id                     UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    muvekkil_id                 UUID NOT NULL REFERENCES muvekkil(id) ON DELETE RESTRICT,
    dosya_no                    TEXT NOT NULL,
    baslik                      TEXT NOT NULL,
    dava_turu                   TEXT,
    durum                       TEXT NOT NULL DEFAULT 'acik'
                                CHECK (durum IN ('acik', 'kapali', 'beklemede')),
    olusturan_kullanici_id      UUID NOT NULL REFERENCES kullanici(id),
    olusturma                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    guncelleme                  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (buro_id, dosya_no)
);
CREATE INDEX idx_dava_buro ON dava_dosyasi(buro_id);
CREATE INDEX idx_dava_muvekkil ON dava_dosyasi(muvekkil_id);

CREATE TABLE dosya_erisim (
    dava_dosyasi_id     UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    kullanici_id        UUID NOT NULL REFERENCES kullanici(id) ON DELETE CASCADE,
    rol                 TEXT NOT NULL CHECK (rol IN ('sorumlu', 'inceleyen')),
    verilme             TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (dava_dosyasi_id, kullanici_id)
);
CREATE INDEX idx_erisim_kullanici ON dosya_erisim(kullanici_id);

-- 3. BELGE VE SAYFA ---------------------------------------

CREATE TABLE belge (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buro_id                     UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    dava_dosyasi_id             UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE RESTRICT,
    orijinal_ad                 TEXT NOT NULL,
    mime_tur                    TEXT NOT NULL CHECK (mime_tur IN (
                                    'application/pdf',
                                    'application/vnd.openxmlformats-officedocument.wordprocessingml.document')),
    depolama_anahtari           TEXT NOT NULL UNIQUE,
    sha256_ozet                 CHAR(64) NOT NULL,
    sayfa_sayisi                INTEGER CHECK (sayfa_sayisi IS NULL OR sayfa_sayisi > 0),
    kategori                    TEXT,
    belge_tarihi                DATE,
    belge_tarihi_kaynagi        TEXT CHECK (belge_tarihi_kaynagi IN ('metin', 'kullanici')),
    durum                       TEXT NOT NULL DEFAULT 'yuklendi'
                                CHECK (durum IN ('yuklendi', 'isleniyor', 'hazir', 'hata')),
    yukleyen_kullanici_id       UUID NOT NULL REFERENCES kullanici(id),
    yuklenme                    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (dava_dosyasi_id, sha256_ozet)   -- aynı dosyanın tekrar yüklenmesini engeller
);
CREATE INDEX idx_belge_dava ON belge(dava_dosyasi_id);
CREATE INDEX idx_belge_buro ON belge(buro_id);

CREATE TABLE belge_sayfa (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belge_id            UUID NOT NULL REFERENCES belge(id) ON DELETE CASCADE,
    sayfa_no            INTEGER NOT NULL CHECK (sayfa_no > 0),
    metin               TEXT NOT NULL DEFAULT '',
    metin_kaynagi       TEXT NOT NULL CHECK (metin_kaynagi IN ('dogrudan', 'ocr')),
    ocr_guven_skoru     REAL CHECK (ocr_guven_skoru IS NULL OR (ocr_guven_skoru BETWEEN 0 AND 1)),
    UNIQUE (belge_id, sayfa_no)
);
-- Tam metin araması (Türkçe morfoloji için ayrı çözüm değerlendirilmeli)
CREATE INDEX idx_sayfa_metin ON belge_sayfa USING GIN (to_tsvector('simple', metin));

-- 4. İŞLEME VE ANALİZ -------------------------------------

CREATE TABLE isleme_gorevi (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    belge_id        UUID NOT NULL REFERENCES belge(id) ON DELETE CASCADE,
    adim            TEXT NOT NULL CHECK (adim IN ('metin_cikarma', 'ocr', 'bolme', 'analiz')),
    durum           TEXT NOT NULL DEFAULT 'bekliyor'
                    CHECK (durum IN ('bekliyor', 'calisiyor', 'tamam', 'hata')),
    hata_mesaji     TEXT,
    tekrar_sayisi   INTEGER NOT NULL DEFAULT 0,
    baslangic       TIMESTAMPTZ,
    bitis           TIMESTAMPTZ
);
CREATE INDEX idx_gorev_belge ON isleme_gorevi(belge_id);

CREATE TABLE analiz_calistirmasi (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    buro_id                     UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    dava_dosyasi_id             UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    kapsam                      TEXT NOT NULL CHECK (kapsam IN ('tek_belge', 'coklu_belge')),
    belge_id                    UUID REFERENCES belge(id) ON DELETE SET NULL,
    model_saglayici             TEXT NOT NULL,
    model_adi                   TEXT NOT NULL,
    prompt_surumu               TEXT NOT NULL,
    calistiran_kullanici_id     UUID NOT NULL REFERENCES kullanici(id),
    baslangic                   TIMESTAMPTZ NOT NULL DEFAULT now(),
    bitis                       TIMESTAMPTZ,
    durum                       TEXT NOT NULL DEFAULT 'calisiyor'
                                CHECK (durum IN ('calisiyor', 'tamam', 'hata'))
);
CREATE INDEX idx_analiz_dava ON analiz_calistirmasi(dava_dosyasi_id);

-- 5. BULGULAR VE KAYNAKLAR --------------------------------

CREATE TABLE bulgu (
    id                          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    analiz_calistirmasi_id      UUID NOT NULL REFERENCES analiz_calistirmasi(id) ON DELETE CASCADE,
    dava_dosyasi_id             UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    tur                         TEXT NOT NULL CHECK (tur IN (
                                    'kisi', 'kurum', 'tarih', 'tutar', 'iddia',
                                    'onemli_ifade', 'eksik_bilgi', 'uyusmazlik')),
    ozet                        TEXT NOT NULL,
    deger                       JSONB NOT NULL DEFAULT '{}'::jsonb,
    guven_seviyesi              TEXT NOT NULL CHECK (guven_seviyesi IN ('dusuk', 'orta', 'yuksek')),
    dogrulama_durumu            TEXT NOT NULL DEFAULT 'otomatik'
                                CHECK (dogrulama_durumu IN ('otomatik', 'inceleniyor', 'onaylandi', 'reddedildi')),
    olusturma                   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_bulgu_dava_tur ON bulgu(dava_dosyasi_id, tur);
CREATE INDEX idx_bulgu_deger ON bulgu USING GIN (deger);

CREATE TABLE kaynak_alinti (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bulgu_id                UUID NOT NULL REFERENCES bulgu(id) ON DELETE CASCADE,
    belge_id                UUID NOT NULL REFERENCES belge(id) ON DELETE CASCADE,
    belge_sayfa_id          UUID NOT NULL REFERENCES belge_sayfa(id) ON DELETE CASCADE,
    alinti_metni            TEXT NOT NULL,
    karakter_baslangic      INTEGER CHECK (karakter_baslangic IS NULL OR karakter_baslangic >= 0),
    karakter_bitis          INTEGER,
    CHECK (karakter_bitis IS NULL OR karakter_baslangic IS NULL OR karakter_bitis >= karakter_baslangic)
);
CREATE INDEX idx_alinti_bulgu ON kaynak_alinti(bulgu_id);
CREATE INDEX idx_alinti_sayfa ON kaynak_alinti(belge_sayfa_id);

CREATE TABLE bulgu_inceleme (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bulgu_id        UUID NOT NULL REFERENCES bulgu(id) ON DELETE CASCADE,
    kullanici_id    UUID NOT NULL REFERENCES kullanici(id),
    karar           TEXT NOT NULL CHECK (karar IN ('onay', 'red', 'duzeltme')),
    notu            TEXT,
    tarih           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_inceleme_bulgu ON bulgu_inceleme(bulgu_id);

-- 6. UYUŞMAZLIK -------------------------------------------

CREATE TABLE uyusmazlik (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dava_dosyasi_id         UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    tur                     TEXT NOT NULL CHECK (tur IN ('tarih', 'tutar', 'kisi_kurum')),
    ilgili_bulgu_1_id       UUID NOT NULL REFERENCES bulgu(id) ON DELETE CASCADE,
    ilgili_bulgu_2_id       UUID NOT NULL REFERENCES bulgu(id) ON DELETE CASCADE,
    aciklama                TEXT NOT NULL,
    ciddiyet                TEXT NOT NULL CHECK (ciddiyet IN ('dusuk', 'orta', 'yuksek')),
    durum                   TEXT NOT NULL DEFAULT 'acik'
                            CHECK (durum IN ('acik', 'incelendi', 'cozuldu')),
    CHECK (ilgili_bulgu_1_id <> ilgili_bulgu_2_id)
);
CREATE INDEX idx_uyusmazlik_dava ON uyusmazlik(dava_dosyasi_id);

-- 7. ZAMAN ÇİZELGESİ VE DELİL HARİTASI --------------------

CREATE TABLE olay (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dava_dosyasi_id     UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    tarih               DATE,
    tarih_kesinligi     TEXT NOT NULL CHECK (tarih_kesinligi IN ('tam', 'ay', 'yil', 'tahmini')),
    baslik              TEXT NOT NULL,
    aciklama            TEXT,
    kaynak_bulgu_id     UUID REFERENCES bulgu(id) ON DELETE SET NULL
);
CREATE INDEX idx_olay_dava_tarih ON olay(dava_dosyasi_id, tarih);

CREATE TABLE iddia (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    dava_dosyasi_id     UUID NOT NULL REFERENCES dava_dosyasi(id) ON DELETE CASCADE,
    metin               TEXT NOT NULL,
    taraf               TEXT NOT NULL CHECK (taraf IN ('davaci', 'davali', 'diger')),
    olusturma           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_iddia_dava ON iddia(dava_dosyasi_id);

CREATE TABLE delil_baglantisi (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    iddia_id                UUID NOT NULL REFERENCES iddia(id) ON DELETE CASCADE,
    kaynak_alinti_id        UUID NOT NULL REFERENCES kaynak_alinti(id) ON DELETE CASCADE,
    iliski                  TEXT NOT NULL CHECK (iliski IN ('destekliyor', 'celistiriyor', 'ilgili')),
    notu                    TEXT,
    dogrulama_durumu        TEXT NOT NULL DEFAULT 'otomatik'
                            CHECK (dogrulama_durumu IN ('otomatik', 'inceleniyor', 'onaylandi', 'reddedildi')),
    UNIQUE (iddia_id, kaynak_alinti_id)
);

-- 8. DENETİM KAYDI ----------------------------------------

CREATE TABLE denetim_kaydi (
    id              BIGSERIAL PRIMARY KEY,
    buro_id         UUID NOT NULL REFERENCES buro(id) ON DELETE RESTRICT,
    kullanici_id    UUID REFERENCES kullanici(id) ON DELETE SET NULL,
    eylem           TEXT NOT NULL CHECK (eylem IN (
                        'goruntuleme', 'yukleme', 'silme', 'onay', 'reddetme', 'disa_aktarim')),
    hedef_tur       TEXT NOT NULL,
    hedef_id        UUID,
    ip_adresi       INET,
    zaman           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_denetim_buro_zaman ON denetim_kaydi(buro_id, zaman);

-- Denetim kaydı yalnızca eklenebilir olsun. Bu kısıt uygulama rolüne uygulanmalıdır;
-- tablo sahibi rol bu kısıtı aşabilir.
REVOKE UPDATE, DELETE ON denetim_kaydi FROM PUBLIC;
