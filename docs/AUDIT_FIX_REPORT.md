# Laporan Audit & Remediasi CABAI-KMS (5 Temuan)

**Tanggal:** 27 Oktober 2026  
**Repositori:** `AgenticAI_CabaiKMS`  
**Author:** `Muhammad Rifqi Setiawan`  
**Branch:** `fix/audit-findings` (bercabang dari `d48002a`)  
**Database Live:** `cabai_kms` (Port 5432) — *Status: 100% Utuh & Tidak Dimutasi*  
**Database Uji:** `cabai_kms_test` (Port 5432)  

---

## 1. Ringkasan Eksekutif & Status Temuan

| No | Temuan Audit | Status | Keterangan Singkat |
|---|---|---|---|
| 1 | Migrasi JSONB 0002 belum diterapkan di DB live | **BLOCKED-MENUNGGU-PERSETUJUAN** | Backup live selesai (`pg_dump` 2.0MB), dry-run berhasil di `cabai_kms_test` (manifest rekonsiliasi pas 78 rows), menunggu persetujuan Rifqi sebelum `--apply` live. |
| 2 | Service masih menjalankan kode lama | **BLOCKED-MENUNGGU-PERSETUJUAN** | Terbukti service start 16 & 19 Okt (sebelum commit 20-21 Okt), endpoint `/documents` 404. Prosedur restart + rollback siap, menunggu migrasi live. |
| 3 | `can_overwrite` tidak pernah dipakai | **DONE** | Logika `can_overwrite` diterapkan pada planner (`DocumentPlanner.plan_records`) dan guard commit (`DocumentRepository.commit`), review item `UNIT_MISMATCH`/`OVERWRITE_BLOCKED` dibuat jika diblok, 5 skenario uji lulus 100%. |
| 4 | Nilai lama hilang saat ditimpa | **DONE** | Migrasi aditif `0003` (`kms.document_attribute_changes`) dibuat dengan trigger `reject_mutation` (append-only) dan hak akses `cabai_app`. Pencatatan otomatis di transaksi commit. Diuji di `cabai_kms_test`. |
| 5 | Persistensi atribut baru belum terbukti | **BLOCKED-MENUNGGU-PERSETUJUAN** | Terbukti dengan tes bahwa `AttributeCatalog` hilang saat proses restart. Rancangan skema tabel persistensi di DB diusulkan, menunggu persetujuan sebelum implementasi. |

---

## 2. Rincian Pelaksanaan Per Temuan

### TEMUAN 1 — Migrasi JSONB 0002 di DB Live
- **Fakta Awal:** `kms.schema_migrations` pada `cabai_kms` hanya berisi versi `0001`. Tabel `kms.knowledge_documents` belum ada. Data legacy berisi 3 acquisition runs dan 78 baris `variety_character_values`.
- **Langkah 1a (Backup Live):**
  - Perintah: `pg_dump -h 127.0.0.1 -U postgres -d cabai_kms -F p -f ~/backups/cabai_kms_20261027_133741.sql`
  - Berkas: `~/backups/cabai_kms_20261027_133741.sql`
  - Ukuran: `2.0 MB` (2.059.573 bytes)
  - SHA-256: `79baded1f052a32d5cc8d5a30d06805403b01f2f02bd9539da0700d719dfbb2f`
- **Langkah 1b (Dry-Run terhadap Salinan Test DB):**
  - Backup direstore ke database uji `cabai_kms_test`.
  - Dijalankan:
    ```bash
    .venv-kms/bin/python scripts/migrate_kms_documents.py --dry-run \
      --db-url "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp" \
      --manifest-output "docs/migration_manifest_dryrun.json"
    ```
- **Langkah 1c (Hasil Rekonsiliasi Manifest):**
  - `total_legacy_rows`: **78**
  - `mapped_count`: **0**
  - `quarantine_count`: **78**
  - `rejected_count`: **0**
  - `mapped_documents_count`: **0**
  - **Invarian Akuntansi:** `total_legacy_rows (78) == mapped (0) + quarantine (78) + rejected (0)` $\rightarrow$ **TERPENUHI TEPAT**.
  - **Alasan Karantina:** Seluruh 78 baris masuk karantina dengan alasan:  
    `"Unresolved location: missing or invalid administrative habitat provenance"` (`raw_address: null`).  
    *Penjelasan teknis:* Pada skema legacy, data dimasukkan tanpa pencatatan administratif desa/kecamatan/kabupaten yang tervalidasi. Dalam model dokumen JSONB, dokumen dikelompokkan berdasarkan `(variety_id, habitat_id)`. Data tanpa asal wilayah sah dialihkan ke antrean review karantina dan tidak dibuang.
- **Commit:** `85945a7` — *docs(kms): add dry-run migration reconciliation manifest for legacy data (temuan 1)*

---

### TEMUAN 2 — Bukti Service Masih Menjalankan Kode Lama
- **Bukti 1 (Waktu Start Proses vs Tanggal Commit):**
  - `cabai-kms-api.service` (PID 3841508): Aktif sejak **Jumat, 16 Oktober 2026 pukul 14:57:38 WIB**.
  - `cabai-kms.service` (Streamlit, PID 839016): Aktif sejak **Senin, 19 Oktober 2026 pukul 09:32:39 WIB**.
  - Commit JSONB & Document API (`648ee66`, `cf683b9`, `1d47fc8`, `3d6e3c5`, `d48002a`) baru di-commit pada rentang **20 Oktober 2026 s.d. 21 Oktober 2026**.
  - Selisih waktu: Service API berjalan 4 hari **sebelum** kode dokumen ada di repository!
- **Bukti 2 (Uji HTTP Endpoint Langsung):**
  - Permintaan: `curl -i http://127.0.0.1:8093/documents`
  - Respons: `HTTP/1.1 404 Not Found` `{"detail":"Not Found"}`
  - Kesimpulan: Endpoint dokumen belum termuat pada proses Uvicorn yang sedang berjalan.
- **Prosedur Restart Terencana (Hanya setelah migrasi live disetujui):**
  ```bash
  systemctl --user restart cabai-kms-api.service
  systemctl --user restart cabai-kms.service
  ```
- **Rencana Rollback:**
  Jika restart mengalami crash atau galat runtime:
  ```bash
  # 1. Matikan service
  systemctl --user stop cabai-kms-api.service cabai-kms.service
  # 2. Kembalikan kode ke HEAD awal jika diperlukan
  git checkout d48002a
  # 3. Nyalakan kembali service
  systemctl --user start cabai-kms-api.service cabai-kms.service
  ```

---

### TEMUAN 3 — Penegakan `can_overwrite` pada Planner dan Guard Commit
- **Masalah:** `src/storage/attribute_policy.py` memiliki fungsi `AttributePolicy.can_overwrite`, namun `DocumentPlanner.plan_records` menimpa `doc_attributes[attr_id]` secara langsung, dan `DocumentRepository.commit` menimpa dengan `merged_attrs.update(incoming)`.
- **Perbaikan yang Diterapkan:**
  1. Pada `src/storage/document_contracts.py`: Menambahkan kategori review `"OVERWRITE_BLOCKED"` dan `"UNIT_MISMATCH"` ke dalam `DocumentReviewItem.category`.
  2. Pada `src/storage/document_planner.py`:
     - Saat memproses baris atribut, sistem memeriksa apakah atribut sudah ada di dokumen (`attr_id in doc_attributes`).
     - Jika sudah ada, sistem mengevaluasi `self.policy.can_overwrite(existing_attr, incoming_attr)`.
     - Jika evaluasi `False`: atribut lama **dipertahankan utuh**, dan dibuat `DocumentReviewItem` bertatus `pending` dengan kategori `UNIT_MISMATCH` (jika satuan berbeda dimensi) atau `OVERWRITE_BLOCKED` (jika tipe/resolusi tidak sesuai) yang memuat nilai lama dan nilai baru di `raw_values` dan `payload`.
     - Jika evaluasi `True`: atribut baru diizinkan menimpa `doc_attributes[attr_id]`.
  3. Pada `src/storage/document_repository.py`:
     - Saat menggabungkan atribut di `commit`, sistem tidak lagi menggunakan `update()` buta.
     - Setiap atribut diperiksa dengan `policy.can_overwrite(exist_av, inc_av)`. Jika `False`, atribut lama dipertahankan (guard protektif).
- **Pengujian (Semua 5 Skenario Lulus 100%):**
  1. `test_can_overwrite_unit_sama_allowed`: cm vs cm $\rightarrow$ diizinkan.
  2. `test_can_overwrite_unit_beda_dimensi_blocked_to_review`: cm vs kg $\rightarrow$ diblok, menghasilkan review item `UNIT_MISMATCH`, nilai lama utuh.
  3. `test_can_overwrite_tipe_beda_blocked_to_review`: number vs text $\rightarrow$ diblok, menghasilkan review item `OVERWRITE_BLOCKED`, nilai lama utuh.
  4. `test_nilai_human_review_tidak_diturunkan_oleh_auto_accept`: pengukuran yang membutuhkan review tidak dapat menimpa nilai dokumen secara otomatis.
  5. `test_varietas_lokasi_sama_atribut_tambahan`: varietas + lokasi sama dengan atribut tambahan $\rightarrow$ atribut lama utuh, atribut baru masuk, versi dokumen naik dari 1 menjadi 2.
- **Commit:** `9f9b1f8` — *fix(storage): enforce can_overwrite policy in document planner and commit merge (temuan 3)*

---

### TEMUAN 4 — Riwayat Nilai Lama yang Ditimpa (`document_attribute_changes`)
- **Masalah:** Dokumen JSONB dirancang tanpa array riwayat internal (sesuai aturan A14), dan `audit_trace` membuang payload dokumen untuk efisiensi ruang. Nilai atribut lama hilang saat terjadi pembaruan.
- **Perbaikan yang Diterapkan:**
  1. Membuat berkas migrasi DDL aditif baru: `schema_0003_attribute_changes.sql`:
     ```sql
     CREATE TABLE IF NOT EXISTS kms.document_attribute_changes (
       id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
       doc_id text NOT NULL,
       attribute_id text NOT NULL,
       old_value jsonb NOT NULL,
       new_value jsonb NOT NULL,
       run_id text NOT NULL,
       actor text NOT NULL,
       created_at timestamptz NOT NULL DEFAULT now()
     );
     CREATE INDEX IF NOT EXISTS document_attribute_changes_doc_idx ON kms.document_attribute_changes (doc_id);
     CREATE INDEX IF NOT EXISTS document_attribute_changes_attr_idx ON kms.document_attribute_changes (attribute_id);
     CREATE INDEX IF NOT EXISTS document_attribute_changes_run_idx ON kms.document_attribute_changes (run_id);
     CREATE TRIGGER reject_change BEFORE UPDATE OR DELETE ON kms.document_attribute_changes FOR EACH ROW EXECUTE FUNCTION kms.reject_mutation();
     CREATE TRIGGER reject_truncate BEFORE TRUNCATE ON kms.document_attribute_changes FOR EACH STATEMENT EXECUTE FUNCTION kms.reject_mutation();
     REVOKE ALL ON kms.document_attribute_changes FROM PUBLIC;
     GRANT SELECT, INSERT ON kms.document_attribute_changes TO cabai_app;
     ```
  2. Mendaftarkan migrasi `0003` di `src/storage/migrate.py`.
  3. Mengimplementasikan `_record_attribute_change` di `src/storage/document_repository.py`: dieksekusi di dalam transaksi `commit` yang sama setiap kali atribut existing mengalami perubahan nilai (`exist_dict != inc_dict`).
  4. Menambahkan tes integrasi pada database `cabai_kms_test`:
     - `test_document_attribute_changes_logged_on_commit`: memverifikasi pencatatan `doc_id`, `attribute_id`, `old_value`, `new_value`, `run_id`, dan `actor`.
     - `test_document_attribute_changes_trigger_rejects_mutation`: memverifikasi trigger `reject_mutation` memblokir `UPDATE`, `DELETE`, dan `TRUNCATE`.
- **Status Database Live:** File migrasi `schema_0003_attribute_changes.sql` **hanya dibuat dan diuji di DB test**, belum diterapkan ke database live `cabai_kms`.
- **Commit:** `a7ac9ed` — *feat(storage): implement additive migration 0003 document attribute changes ledger (temuan 4)*

---

### TEMUAN 5 — Investigasi Persistensi Katalog Atribut Baru
- **Hasil Investigasi & Bukti:**
  - `AttributeCatalog` pada `src/storage/attribute_policy.py` dibangun secara *in-memory* dari `_build_seed_definitions()` yang membaca berkas `data/canonical/template_kanonik.xlsx`.
  - Pada alur review `DocumentRepository.resolve_review` (`src/storage/document_repository.py:638-644`), saat kurator menyetujui item review bertipe `NEW_ATTRIBUTE`:
    ```python
    else:
        decision_status = dec_dict.get("status", "approved")
        target_item.status = "approved" if decision_status != "rejected" else "rejected"
        target_item.decision = dec_dict
    ```
    Sistem hanya mengubah status item review di dalam payload draft menjadi `"approved"`. Sistem **tidak pernah** menyimpan definisi atribut baru tersebut ke tabel database manapun, dan **tidak menulis** kembali ke file Excel kanonik.
  - **Bukti Tes (`tests/storage/test_attribute_catalog_persistence.py`):**
    Tes `test_approved_new_attribute_does_not_persist_across_restarts` membuktikan bahwa atribut yang didaftarkan pada proses ke-1 tidak dapat ditemukan (`lookup is None`) saat proses di-restart / instansiasi ulang `AttributeCatalog()`.
- **Rancangan Usulan Persistensi Katalog di Database:**
  Untuk mempertahankan atribut baru pasca-restart tanpa mengubah file template kanonik:
  1. **Tabel Aditif Baru (`kms.catalog_attributes`):**
     ```sql
     CREATE TABLE IF NOT EXISTS kms.catalog_attributes (
       attribute_id text PRIMARY KEY,
       canonical_key text NOT NULL UNIQUE,
       label text NOT NULL,
       organ text NOT NULL,
       value_type text NOT NULL DEFAULT 'text',
       unit text,
       description text,
       development_stage text,
       aliases text[] NOT NULL DEFAULT '{}',
       approved_by_run text,
       created_at timestamptz NOT NULL DEFAULT now()
     );
     CREATE INDEX IF NOT EXISTS catalog_attributes_label_idx ON kms.catalog_attributes (lower(label));
     GRANT SELECT, INSERT ON kms.catalog_attributes TO cabai_app;
     ```
  2. **Pemuatan Saat Start:** `AttributeCatalog.__init__` memuat seed dari template kanonik, lalu melakukan `SELECT * FROM kms.catalog_attributes` untuk menggabungkan atribut dinamis yang telah disetujui.
  3. **Penyimpanan Saat Approve:** Ketika kurator menyetujui item review `NEW_ATTRIBUTE`, endpoint/metode `resolve_review` menyimpan definisi atribut ke `kms.catalog_attributes`.
- **Status:** **BLOCKED-MENUNGGU-PERSETUJUAN**. Belum ada file migrasi atau kode runtime yang diubah untuk Temuan 5 sebelum rancangan ini disetujui oleh Rifqi.
- **Commit:** `b3c1f89` — *test(catalog): prove catalog in-memory loss across process restarts (temuan 5)*

---

## 3. Daftar Commit dan Git Diff Stat

### A. Riwayat Commit (`git log -n 4 --oneline`)
```text
b3c1f89 test(catalog): prove catalog in-memory loss across process restarts (temuan 5)
a7ac9ed feat(storage): implement additive migration 0003 document attribute changes ledger (temuan 4)
9f9b1f8 fix(storage): enforce can_overwrite policy in document planner and commit merge (temuan 3)
85945a7 docs(kms): add dry-run migration reconciliation manifest for legacy data (temuan 1)
```

### B. Git Diff Stat (`git diff --stat d48002a..HEAD`)
```text
 docs/migration_manifest_dryrun.json                | 1031 ++++++++++++++++++++
 schema_0003_attribute_changes.sql                  |   39 +
 src/storage/document_contracts.py                  |    2 +
 src/storage/document_planner.py                    |   71 +-
 src/storage/document_repository.py                 |   66 +-
 src/storage/migrate.py                             |    1 +
 .../storage/test_attribute_catalog_persistence.py  |   46 +
 tests/storage/test_attribute_history_ledger.py     |  238 +++++
 tests/storage/test_attribute_overwrite.py          |  319 ++++++
 9 files changed, 1800 insertions(+), 13 deletions(-)
```

---

## 4. Hasil Eksekusi Test Lengkap

**Perintah:**
```bash
.venv-kms/bin/pytest tests/storage tests/kms tests/test_document_e2e.py tests/ui tests/vision tests/test_ui.py tests/test_orchestrator.py tests/test_pipeline_runner.py
```

**Ringkasan Hasil:**
- Baseline Awal: **380 passed, 1 skipped** (316 passed + 64 passed).
- Hasil Akhir: **388 passed, 1 skipped, 0 failed** (bertambah 8 tes baru untuk temuan 3, 4, 5).
- Nol tes yang dilemahkan, dihapus, atau di-skip demi kelulusan.

---

## 5. Yang BELUM Dilakukan & Perintah Eksekusi Persis

Sesuai aturan keras, tindakan berikut **belum dijalankan pada lingkungan live** dan menunggu persetujuan eksplisit:

1. **Penerapan Migrasi 0002 & 0003 ke DB Live `cabai_kms`:**
   ```bash
   DATABASE_ADMIN_URL="postgresql+psycopg://postgres@127.0.0.1/cabai_kms" .venv-kms/bin/python src/storage/migrate.py
   ```
2. **Eksekusi Migrasi Data Legacy ke JSONB di DB Live `cabai_kms`:**
   ```bash
   .venv-kms/bin/python scripts/migrate_kms_documents.py --apply --db-url "postgresql+psycopg://postgres@127.0.0.1/cabai_kms"
   ```
3. **Restart Service Production CABAI-KMS:**
   ```bash
   systemctl --user restart cabai-kms-api.service
   systemctl --user restart cabai-kms.service
   ```
4. **Implementasi Persistensi Katalog Atribut (Temuan 5):**
   Menunggu arahan apakah rancangan tabel `kms.catalog_attributes` disetujui.
