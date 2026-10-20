# Panduan Operasional Migrasi Dokumen JSONB Cabai-KMS (Tahap S8)

Dokumen ini merupakan panduan teknis dan operasional untuk migrasi data relasional historis (legacy) Cabai-KMS menuju arsitektur penyimpanan dokumen JSONB terstruktur (`kms.knowledge_documents`), penanganan karantina data tanpa habitat definitif, serta prosedur penanganan rollback pra dan pasca-cutover.

---

## 1. Latar Belakang & Prinsip Rekayasa

Arsitektur penyimpanan Cabai-KMS berevolusi dari model relasional berorientasi nilai varietas tunggal menjadi dokumen pengetahuan agregat terstruktur `(variety_id, habitat_id)` berbasis JSONB.

Prinsip migrasi data legacy:
1. **Safety First (Zero Destructive Purge):** Kode produk dan skrip migrasi dilarang keras memuat perintah pembersihan destruktif seperti penghapusan tabel otomatis.
2. **Accountable Dry-Run by Default:** Setiap pemanggilan skrip `scripts/migrate_kms_documents.py` tanpa parameter mutasi eksplisit secara default berjalan dalam mode `--dry-run`.
3. **Reconciliation Manifest Integrity:** Setiap baris data legacy wajib terhitung secara definitif (`total == mapped + quarantine + rejected`).
4. **Habitat Provenance Guard:** Data legacy yang tidak memiliki metadata lokasi administratif desa definitif wajib dialihkan ke antrean karantina (*quarantine*), bukan direplikasi secara liar ke seluruh habitat varietas terkait.
5. **Idempotensi Eksekusi:** Skrip migrasi dapat dijalankan berulang kali tanpa menghasilkan duplikasi dokumen atau error konflik kunci.

---

## 2. Antarmuka CLI & Argumen Skrip

Skrip migrasi dioperasikan melalui berkas `scripts/migrate_kms_documents.py`:

```bash
# Mode default: Dry-run akuntabel (tanpa menulis ke basis data)
python scripts/migrate_kms_documents.py --dry-run

# Mode dry-run dengan penyimpanan berkas manifest rekonsiliasi
python scripts/migrate_kms_documents.py --dry-run --manifest-output /tmp/migration_manifest.json

# Mode eksekusi transaksional (Apply)
python scripts/migrate_kms_documents.py --apply --manifest-output /tmp/migration_applied_manifest.json

# Simulasi Rollback Pra-cutover
python scripts/migrate_kms_documents.py --rollback --mode pre-cutover

# Simulasi Rollback Pasca-cutover (dengan ekspor recovery staging)
python scripts/migrate_kms_documents.py --rollback --mode post-cutover --export-staging-path /tmp/kms_rollback_recovery.json
```

### Parameter yang Didukung:
- `--dry-run`: Menjalankan evaluasi pemetaan dan kalkulasi manifest tanpa mutasi basis data (perilaku default).
- `--apply`: Mengaktifkan persistensi transaksional ke tabel `kms.knowledge_documents`.
- `--manifest-output <PATH>`: Menentukan lokasi penyimpanan berkas keluaran manifest JSON hasil rekonsiliasi.
- `--db-url <URL>`: Menentukan URL koneksi PostgreSQL target (opsional, default membaca variabel lingkungan `DATABASE_URL` atau `TEST_DATABASE_URL`).
- `--actor <NAMA>`: Menetapkan identitas aktor audit (`kms.actor`) untuk pencatatan transaksi PostgreSQL.
- `--rollback`: Menjalankan prosedur simulasi pemulihan / rollback.
- `--mode <pre-cutover|post-cutover>`: Memilih skenario rollback yang akan dievaluasi.
- `--export-staging-path <PATH>`: Menentukan path berkas ekspor data staging saat rollback pasca-cutover.

---

## 3. Manifes Rekonsiliasi & Akuntansi Data Total

Setiap eksekusi migrasi menghasilkan dokumen manifest terstruktur yang menjamin akuntansi 100% dari baris data legacy:

$$\text{total\_legacy\_rows} = \text{mapped\_count} + \text{quarantine\_count} + \text{rejected\_count}$$

### Struktur Manifes:
- `dry_run` (boolean): Menandai apakah eksekusi dilakukan tanpa perubahan basis data.
- `summary` (object):
  - `total_legacy_rows`: Total baris pada tabel legacy `kms.variety_character_values`.
  - `mapped_count`: Jumlah baris legacy yang berhasil dipetakan ke atribut dokumen.
  - `quarantine_count`: Jumlah baris legacy tanpa lokasi valid yang dialihkan ke karantina.
  - `rejected_count`: Jumlah baris legacy yang ditolak akibat data korup atau inkonsistensi taksonomi.
  - `mapped_documents_count`: Jumlah entitas `KnowledgeDocument` gabungan `(variety_id, habitat_id)` yang terbentuk.
- `mapped_documents` (array): Representasi JSON dari dokumen pengetahuan yang siap atau telah disimpan.
- `quarantine_items` (array): Rincian item data yang masuk status karantina beserta alasan penahanan.
- `rejected_items` (array): Rincian data yang gagal diproses beserta catatan diagnostik kegagalan.

---

## 4. Alur Karantina Data Legacy (Quarantine Workflow)

### Kriteria Masuk Karantina:
Baris data pada tabel legacy `kms.variety_character_values` dialihkan ke antrean karantina apabila:
1. Tidak memiliki rekaman `value_observations` terkait.
2. Metadata `evidence` pada `value_observations` tidak memuat alamat lapangan (`raw_address` bernilai `null` atau kosong).
3. Hierarki administratif desa (`province`, `regency`, `district`, `village`) tidak lengkap dan gagal dicocokkan dengan registry wilayah administratif kurasi (`src/storage/registries/administrative_regions.json`).
4. Alamat lapangan ambigu atau mengandung konflik nama wilayah tanpa resolusi definitif.

### Larangan Replikasi Atribut:
Sesuai prinsip integritas ilmiah (PRD I7), jika suatu varietas (contoh: *Cabai rawit*) telah memiliki dokumen di *Desa Hargobinangun*, nilai legacy varietas tersebut yang tidak memiliki lokasi lapangan **DILARANG KERAS** ditempelkan secara otomatis ke *Desa Hargobinangun*. Seluruh nilai tanpa lokasi wajib ditahan di `quarantine_items` sampai kurator menetapkan lokasi sampling yang tepat melalui antarmuka review kurator.

---

## 5. Prosedur Rollback & Rencana Kontinjensi

Kebijakan rollback dirancang berdasarkan status tahapan implementasi:

### Skenario 1: Pra-Cutover (Pre-Cutover Rollback)
- **Kondisi:** Sistem baru belum menjadi jalur tulis utama aplikasi produksi; layanan legacy masih menerima operasi baca/tulis normal.
- **Prosedur:**
  1. Hentikan eksekusi skrip migrasi atau batalkan flag pengaktifan JSONB.
  2. Verifikasi keutuhan data pada tabel legacy `kms.variety_character_values` dan `kms.value_observations`.
  3. Dokumen JSONB sementara pada `kms.knowledge_documents` dapat dibersihkan atau dibiarkan tanpa mempengaruhi operasional legacy.
  4. Status pemulihan: **100% lossless**, data historis tetap utuh dan terbaca oleh kueri legacy.

### Skenario 2: Pasca-Cutover (Post-Cutover Rollback)
- **Kondisi:** Write baru JSONB telah terjadi setelah cutover produksi (terdapat penambahan dokumen atau atribut baru pada `kms.knowledge_documents`).
- **Prosedur:**
  1. **Hentikan Penulisan Sementara:** Bekukan sementara lalu lintas penulisan dokumen baru untuk mencegah penumpukan delta yang tidak terakomodasi.
  2. **Ekspor Snapshot Recovery Staging:** Jalankan eksekusi `simulate_rollback --mode post-cutover --export-staging-path <PATH>`. Seluruh dokumen JSONB aktif diekspor ke format staging mandiri.
  3. **Evaluasi Ketidakmungkinan Lossless:** Mengingat skema legacy tabel datar tidak dapat merepresentasikan atribut dinamis multidomain dan hierarki habitat baru, skrip secara eksplisit menetapkan `lossless_guarantee = False`.
  4. **Pilihan Pemulihan:** Tim arsitektur bersama DBA menentukan strategi *forward-fix* (perbaikan skema dokumen JSONB) atau *reverse-migration* terkontrol berbasis data staging yang telah diekspor. Tidak diperkenankan melakukan penghapusan data secara sepihak.

---

## 6. Kebijakan Retensi Tabel Legacy 30 Hari (PRD G2, A19)

Untuk memastikan kelancaran masa transisi arsitektur data:
1. **Masa Transisi 30 Hari:** Seluruh tabel historis (`kms.variety_character_values`, `kms.value_observations`, `kms.draft_revisions`, `kms.acquisition_runs`) **dipertahankan berstatus read-only selama minimal 30 hari** terhitung sejak cutover resmi ke penyimpanan JSONB.
2. **Larangan Purge Otomatis:** Kode produk dilarang keras memicu penghapusan otomatis data historis legacy.
3. **Auditability & Traceability:** Seluruh mutasi dokumen JSONB dicatat secara transparan pada tabel `kms.audit_trace` dengan menyertakan identitas aktor pengubah (`kms.actor`), memastikan setiap langkah migrasi dan review dapat diaudit sepenuhnya.
