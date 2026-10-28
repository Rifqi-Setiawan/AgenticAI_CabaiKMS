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

---

## Addendum: Koreksi Rujukan Teknis

Berikut adalah addendum perbaikan data dan rujukan audit tindak lanjut per 27 Oktober 2026:

1. **Koreksi Ukuran Berkas Backup Live:**
   - Pada Bagian 2 tercatat ukuran cadangan pg_dump live `cabai_kms_20261027_133741.sql` sebesar 2.059.573 byte.
   - Ukuran fisik berkas riil yang diverifikasi pada disk adalah **2.078.582 byte**.
   - Checksum integritas SHA-256 tetap cocok dan identik: `79baded1f052a32d5cc8d5a30d06805403b01f2f02bd9539da0700d719dfbb2f`.

2. **Koreksi Rujukan Baris `resolve_review`:**
   - Rujukan baris cabang resolusi review kategori `OVERWRITE_BLOCKED` dan `UNIT_MISMATCH` pada `src/storage/document_repository.py` yang sebelumnya tercatat di sekitar baris 638-644 telah bergeser ke baris ~578-668 / ~707-712 seiring penambahan blok kontrak dan penanganan spesifik.
   - Alur resolusi kini mendukung 3 aksi terarah: `KEEP_EXISTING` (status rejected, nilai lama utuh), `APPLY_INCOMING` (status approved, resolusi HUMAN_REVIEW), dan `REVISE` (status revised, nilai/satuan terkoreksi). Nilai terlindungi `EXISTING_HUMAN_PROTECTED` wajib diselesaikan oleh peran `curator` disertai alasan (`reason`).

---

## Addendum 2: Perbaikan Audit Ulang Putaran 2 (28 Oktober 2026)

Addendum ini merangkum perbaikan komprehensif atas temuan audit ulang putaran 2 (T-H1 s.d. T-H3 dan T-M1 s.d. T-M5) yang dikerjakan secara test-first di branch terisolasi `fix/audit-followup-2`:

1. **Keputusan Formal D2 & Penggantian PRD A10:**
   - Keputusan arsitektur formal D2 disahkan dan dicatat pada `/srv/hermes-control/decisions/2026-10-27-hr-value-protection-d2.md`.
   - Atribut tersimpan dengan `resolution = "HUMAN_REVIEW"` dilindungi secara permanen (`EXISTING_HUMAN_PROTECTED`) dari penimpaan otomatis oleh `AUTO_ACCEPT`.
   - Aturan historis PRD A10 ("AUTO_ACCEPT boleh menimpa HUMAN_REVIEW") resmi dinyatakan **DIGANTIKAN oleh D2 (27 Okt 2026)** pada seluruh dokumen spesifikasi tanpa menghapus teks historis.

2. **Persetujuan Otoritas Akhir atas 4 Fungsi Tes Lama (Gerbang K1):**
   - Perubahan 4 fungsi tes lama baseline diisolasi secara atomik pada commit `5f6022e`.
   - Waktu Persetujuan: **28 Oktober 2026, 00:36 WIB**.
   - Teks Persetujuan Rifqi: *"setuju gass"* (dan izin modifikasi sintaks tes: *"mengizinkan"*).

3. **Ringkasan Remediasi Temuan Audit Putaran 2:**
   - **T-H1 (Kontrak Jembatan UI -> API):** Menambahkan pembuka body `_unwrap_decision` pada `src/kms_api/app.py` sehingga body bersarang `{"decision": {...}}` dari UI Streamlit maupun photo review dapat diterima secara transparan dan diteruskan sebagai dictionary datar ke repository. Keputusan tanpa `action` dan tanpa `status` ditolak dengan error 422.
   - **T-H2 (Interaktivitas UI Anti-Salah-Satuan):** Menghapus seluruh string alasan hardcode (`"Curator approval"` / `"Curator correction"`). Menambahkan form interaktif dengan input alasan wajib (minimal 10 karakter) serta input nilai dan satuan terkoreksi yang wajib dikonfirmasi kurator. Pada kategori `UNIT_MISMATCH`, tombol *"Terapkan Baru"* dihilangkan untuk mencegah bug fatal konversi satuan (misal "85 kg" menjadi "85 cm").
   - **T-H3 (Pengesahan & Isolasi Tes D2):** Empat fungsi tes baseline lama (`test_attribute_policy.py`, `test_document_repository.py`, `test_document_e2e.py`) diisolasi dalam commit `5f6022e` dan disahkan melalui Gerbang K1.
   - **T-M1 (Hardening Endpoint `/readyz`):** Mengembalikan proteksi autentikasi bearer (`Depends(authenticate)`), memvalidasi keberadaan tabel wajib dan memeriksa integritas checksum tabel migrasi terhadap berkas disk. Menyaring traceback dan pesan internal exception agar tidak bocor ke publik pada respons 503.
   - **T-M2 (Restorasi Perilaku Runner `migrate.py`):** Mengembalikan perilaku kanonik runner migrasi. Menghapus klausa `ON CONFLICT DO UPDATE` dan pengecekan yang mengeksekusi ulang DDL secara diam-diam. Jika migrasi tercatat di DB namun tabel hilang, runner melempar `RuntimeError` eksplisit untuk intervensi manual.
   - **T-M3 (Eliminasi Shim Berbahaya):** Menghapus kelas shim `DocumentDict` dan `RunDict` dari `src/storage/document_repository.py`. Mengubah parameter `resolve_review(..., actor_role=None)` sehingga nilai berstatus `EXISTING_HUMAN_PROTECTED` wajib diselesaikan oleh aktor berhak `curator`.
   - **T-M4 (Validasi Ketat Resolusi Review):** Mencegah no-op diam-diam saat dokumen atau atribut target tidak ditemukan di draft, mewajibkan alasan pada aksi `APPLY_INCOMING` dan `REVISE`, memeriksa kompatibilitas satuan terkoreksi, serta memvalidasi tipe angka.
   - **T-M5 (Tata Kelola Git):** Seluruh perbaikan putaran 2 dikerjakan di branch kerja baru `fix/audit-followup-2` dari base commit `a4bae14`. **Tidak ada commit langsung ke branch main.**

4. **Verifikasi Integritas Checksum Database Live (`cabai_kms`):**
   - Dilakukan pembacaan BACA-SAJA (read-only) pada database live `cabai_kms` (tabel `kms.schema_migrations`):
     * Versi `0001`: `3be3cd5508a4a0f516abcb7e8e89c6af2e8fa413cf2918c03d2950a53e16b7f3` (Cocok 100% dengan berkas disk `schema.sql`)
     * Versi `0002`: `1f8f4fac6cb8f2f0a5c5c430e2880aea8a942da7b46d0dd819b430e4eebcf84a` (Cocok 100% dengan berkas disk `schema_0002_jsonb.sql`)
     * Versi `0003`: `3252f28a719ad1976eb3b00008fc333306d4493332fbdb2dcc0d2b8011a2224b` (Cocok 100% dengan berkas disk `schema_0003_attribute_changes.sql`)
   - Kondisi STOP (d) tidak terpicu; integritas skema database live terbukti 100% valid dan konsisten.

---

## Addendum 3: Koreksi Tata Kelola Git, Pengesahan Tes Ronde 2, dan Peluncuran Ronde 3 (28 Oktober 2026)

Addendum ini mencatat koreksi faktual tata kelola Git, inventarisasi lengkap adaptasi berkas tes lama, pengesahan formal otoritas akhir, serta cakupan kerja Ronde 3:

1. **Koreksi Faktual Tata Kelola Git (Putaran 2):**
   - Pada Addendum 2 butir 3 (T-M5) tertulis kalimat *"Tidak ada commit langsung ke branch main"*.
   - **Koreksi Faktual:** Seluruh commit pengembangan putaran 2 memang dibuat dan diuji secara terisolasi pada branch kerja `fix/audit-followup-2`. Namun, setelah verifikasi Sentinel dinyatakan PASS (`deleg_9ba70538`), branch `fix/audit-followup-2` digabungkan ke `main` melalui **fast-forward merge** (`a4bae14..d0f981b`) dan di-push ke `origin/main` atas persetujuan eksplisit Rifqi (*"setuju gas"*). Layanan systemd produksi kemudian di-restart pada pukul 10:24 WIB (PID 3435596 dan 3435597).

2. **Daftar Hunk Adaptasi Tes Lama di Luar 4 Fungsi D2 & Pengesahan Resmi:**
   Dalam rangka implementasi L3 (penghapusan kelas shim `DocumentDict`/`RunDict`) dan L4 (pengembalian autentikasi `/readyz` dan restorasi tabel via DDL murni), dilakukan adaptasi sintaksis pada tiga berkas tes putaran 1 tanpa melemahkan asersi bisnis:
   - `tests/storage/test_overwrite_review_resolution.py`:
     * Baris 187, 248, 362: Mengubah akses properti `.attributes[...]` menjadi standard dictionary indexing `["attributes"][...]`.
     * Baris 412: Mengubah alias kunci `["draft_payload"]` menjadi `["draft"]`.
   - `tests/storage/test_commit_overwrite_guard.py`:
     * Baris 160, 209, 258, 407, 408: Mengubah akses properti `.attributes[...]` menjadi dictionary indexing `["attributes"][...]`.
   - `tests/storage/test_ledger_and_readiness.py`:
     * Baris 153: Mengubah akses properti `.attributes[...]` menjadi dictionary indexing `["attributes"][...]`.
     * Baris 156 & 247: Memulihkan tabel `kms.document_attribute_changes` langsung menggunakan eksekusi raw DDL `schema_0003_attribute_changes.sql`, bukan memanggil runner `migrate(admin_url)` (karena runner kanonik kini menolak eksekusi ulang DDL bila versi sudah tercatat).
     * Baris 240 & 273: Menambahkan header `Authorization: Bearer <token>` pada pemanggilan endpoint `/readyz` menyusul pengembalian proteksi autentikasi bearer.
   - **Pernyataan Pengesahan Resmi Otoritas Akhir (28 Oktober 2026):**
     > *"Rifqi menyetujui dan mengesahkan seluruh perubahan pada ketiga berkas tes tersebut sebagaimana tercermin pada commit HEAD `d0f981b` sebagai konsekuensi teknis langsung dari penghapusan shim dan pengembalian autentikasi /readyz tanpa pengurangan kekuatan asersi."*

3. **Ruang Lingkup dan Peluncuran Ronde 3:**
   - Menyempurnakan paritas dokumentasi publik (`README.md`, `PROJECT_GUIDE.md`, `KMS_JSONB_MIGRATION.md`).
   - Menerapkan Keputusan Formal D10–D13 terkait sistem klasifikasi gambar varietas baru dengan Antrean Kandidat (`CANDIDATE`).
   - Mengembangkan registri varietas dinamis, fusi sinyal nama file dan visual, migrasi skema aditif `0004` (`kms.image_candidates` & `kms.discarded_images`), API kandidat terotentikasi, antarmuka Streamlit "Kandidat Varietas" & "Dokumen Perlu Habitat", serta harness evaluasi visi.

---

## Addendum 4: Perbaikan Hasil Audit Ronde 3 (Ronde 4, 28 Oktober 2026)

Addendum ini merangkum perbaikan komprehensif atas temuan audit Claude terhadap commit HEAD `dd3a3f2` (F-1 s.d. F-10) yang diselesaikan secara test-first di branch kerja `fix/round4`:

1. **F-1 & F-11 (Hak Akses Role Aplikasi Minimal `cabai_app`):**
   - Dibuat migrasi aditif baru `0005` (`schema_0005_app_grants.sql`) yang memberikan `GRANT DELETE ON kms.knowledge_documents TO cabai_app;` dan `GRANT UPDATE ON kms.discarded_images TO cabai_app;`. Checksum migrasi `0001`–`0004` tetap utuh.
   - Pada `DocumentRepository.resolve_candidate` untuk aksi DISCARD, diubah menjadi `INSERT ... ON CONFLICT (original_sha256) DO NOTHING`.
   - Pada `set_document_habitat`, jika dokumen tujuan belum ada, dilakukan pembaruan in-place (`UPDATE kms.knowledge_documents SET id = :dest_key, habitat_id = :hid, ... WHERE id = :src_key`), menghindari delete+insert dan memerlukan hak `UPDATE` saja.
   - Dibuat fixture pengujian khusus `app_role_db` yang terhubung langsung menggunakan role berhak minimal `cabai_app` untuk memastikan tidak ada perintah SQL yang gagal dengan `permission denied` di lingkungan produksi.

2. **F-2 (Proteksi Anti-Penimpaan Dokumen pada PROMOTE):**
   - Klausa `ON CONFLICT (id) DO UPDATE SET document = EXCLUDED.document` dihapus sepenuhnya dari `resolve_candidate`.
   - Jika dokumen dengan `id = doc_key` sudah terdaftar, server melempar exception `Conflict` eksplisit: *"dokumen sudah ada; gunakan MERGE"*.
   - Dokumen lama beserta atributnya dijamin 100% utuh. Peneliti diarahkan menggunakan MERGE untuk foto varietas yang sama.

3. **F-3 (Pencegahan Penghapusan & Kehilangan Data pada `set_document_habitat`):**
   - Menolak permintaan jika habitat tujuan menghasilkan kunci dokumen yang sama atau bernilai `habitat_unknown` (`InvalidState`).
   - Memvalidasi bahwa dokumen sumber memang berstatus `habitat_unknown = True`.
   - Memeriksa potensi konflik nilai atribut antara dokumen sumber dan tujuan saat proses penggabungan. Jika terjadi pertentangan nilai atribut, operasi ditolak dengan `Conflict` (mewajibkan resolusi kurator manual, tidak dibuang diam-diam).

4. **F-4 & F-9 (Perbaikan API & Pemasangan Antarmuka UI):**
   - Seluruh pemanggilan method privat `client._post` dan `client._get` pada `src/integrations/candidates_ui.py` diganti dengan method resmi `client.request()`.
   - Panel antarmuka `render_candidates_panel` dan `render_habitat_unknown_documents_panel` dipasang secara resmi sebagai tab utama pada `src/ui/pages/4_KMS.py`.
   - Form PROMOTE hanya memperbolehkan pemilihan habitat yang benar-benar terdaftar di database (diambil dari `/documents`) atau sentinel habitat belum diketahui (D11); form teks bebas yang mengarang habitat dieliminasi.
   - Pada endpoint `POST /candidates`, dipasang model Pydantic `CandidateCreateRequest` (otomatis menghasilkan status 422 jika format sha256 64-hex atau organ_part tidak valid) serta dependensi otorisasi `writer` (otomatis menghasilkan 403 Forbidden bagi peran tanpa hak seperti `reader`).
   - Ditambahkan endpoint publik terotentikasi `GET /varieties` yang mengembalikan daftar seluruh nama varietas kanonik terdaftar secara cepat dan akurat.

5. **F-5 (Eliminasi Habitat Karangan):**
   - Pada `resolve_candidate` aksi PROMOTE, jika `habitat_id` diberikan, sistem memverifikasi keberadaannya di tabel `kms.knowledge_documents`. Jika tidak ditemukan, melempar `InvalidState`. Jika tidak diisi, dokumen otomatis memakai identitas unknown resmi (`make_unknown_habitat()`).

6. **F-6, F-7, F-8 (Penyempurnaan Vision Hook & Fusi Tiga Sinyal):**
   - **F-6:** Sesi klasifikasi visual multimodal `VisionSession` kini diberikan opsi lengkap dari registri varietas gabungan (`registry.get_canonical_names()`), sehingga varietas yang baru terdaftar di database tetap dikenali oleh model visi.
   - **F-7:** Seluruh blok `except Exception: pass` pada pengambilan varietas DB dan pengecekan `/discarded` dihapus; kegagalan kini menimbulkan error terlihat. Kegagalan saat memanggil `POST /candidates` mencatat status eksplisit `FAILED_CANDIDATE_RECORD` pada rekaman foto.
   - **F-8:** Logika pengenalan varietas pada `signal_fusion._is_in_registry` diperketat: menghapus pemeriksaan token subset (`tokens.issubset`) dan fuzzy matching. Sinyal hanya mengakui varietas yang cocok persis (exact normalized) dengan nama kanonik atau alias terdaftar.

7. **F-10 (Jejak Versi & Concurrency Guard):**
   - Aksi MERGE pada resolusi kandidat kini mendukung pemeriksaan versi optimistik (`expected_version`). Jika versi dokumen di database telah berubah, operasi dibatalkan dengan status `Conflict`.

---

## Addendum 5: Perbaikan Hasil Audit Ronde 4 (Ronde 5, 28 Oktober 2026)

Addendum ini merangkum penyelesaian temuan audit sisa Ronde 4 (G-1 s.d. G-8) yang dikerjakan secara test-first di branch `fix/round5`:

1. **G-1 (Koreksi HTTPX Kwarg & Penghapusan TypeError):**
   - Mengganti parameter keliru `json_body=...` dengan keyword argument resmi HTTPX `json=...` pada `resolve_candidate_api` dan `set_document_habitat_api`.
   - Menggunakan tanda tangan tegas `resolve_candidate_api(candidate_id, decision, *, client=None)` dan `set_document_habitat_api(doc_key, habitat_payload, *, client=None)` dengan pembungkus fleksibel untuk kompatibilitas ke belakang.
   - Pengujian `tests/kms/test_round5_client_api_ui.py` memvalidasi operasi PROMOTE, MERGE, DISCARD, dan SET_HABITAT secara langsung menggunakan `KmsClient` asli dengan `httpx.Client` terotentikasi, membuktikan tidak ada lagi exception `TypeError: Client.request() got an unexpected keyword argument 'json_body'`.

2. **G-2 (Standarisasi 4-Tingkat Jalur Administratif Habitat):**
   - Server menolak permintaan `set_document_habitat` jika salah satu dari 4 jenjang wilayah administratif (`province_name`, `regency_name`, `district_name`, `village_name`) bernilai `'Unknown'`, tidak diketahui, atau kosong (`InvalidState`).
   - ID habitat dihitung secara deterministik menggunakan fungsi kanonik `compute_habitat_id()` dari `src/storage/identity_resolution.py` mengikuti pola `hab_{regency}_{district}_{village}` yang identik dengan pipeline ekstraksi.

3. **G-3 (Antarmuka PROMOTE/MERGE Bersahabat & Proteksi Versi):**
   - Form PROMOTE menyediakan opsi dropdown dari habitat terdaftar (dengan opsi default `(Habitat Belum Diketahui - D11)`).
   - Form MERGE menyediakan dropdown dokumen terdaftar dan secara otomatis menyertakan `expected_version` dokumen target saat submit. Bila versi dokumen target telah berubah bersamaan, transaksi dibatalkan dengan pesan konflik yang ramah bagi kurator.

4. **G-4 (Pemisahan Petunjuk vs Kecocokan Eksak pada Fusi Sinyal):**
   - Sinyal konteks nama file yang diperoleh dari token subset atau fuzzy matching diberi penanda `is_exact=False`.
   - Pada status visual `OTHER` (model visi meyakini varietas baru), petunjuk non-eksak tidak lagi memicu `REVIEW_MISMATCH`, melainkan diperlakukan sebagai saran nama kandidat (`suggested_candidate_name`) pada antrean `CANDIDATE`. Hanya kecocokan eksak (nama kanonik atau alias terdaftar) yang memicu `REVIEW_MISMATCH` bila visual menyatakan varietas baru.
   - Normalisasi awalan kata umum (`cabai`/`cabe`) pada pembandingan nama memastikan varietas seperti "Cabai Rawit" vs kanonik "Rawit" tetap dikenali sebagai kecocokan eksak (`AUTO_LINK`).

5. **G-5 (Pencatatan Kelebihan Hak Akses pada Migrasi 0005):**
   - Hak `GRANT UPDATE ON kms.discarded_images TO cabai_app;` pada `schema_0005_app_grants.sql` merupakan kelebihan hak akses yang tidak digunakan di runtime (karena operasi DISCARD telah disempurnakan menggunakan `ON CONFLICT (original_sha256) DO NOTHING` yang hanya membutuhkan hak `INSERT`). DDL migrasi 0005 tetap dipertahankan apa adanya di repositori guna menjamin kecocokan checksum dengan database live.
   - Hak `GRANT DELETE ON kms.knowledge_documents TO cabai_app;` tetap sah dan mutlak diperlukan untuk menghapus baris dokumen sumber lama saat digabungkan ke dokumen tujuan pada alur `set_document_habitat`.

6. **G-6 (Jejak Relasional Dokumen Berpindah):**
   - Saat dokumen `habitat_unknown` dipindahkan ke habitat definitif via `set_document_habitat`, server mencatat satu entri jejak relasional pada tabel append-only `kms.document_attribute_changes` dengan penanda `attribute_id = 'habitat_migration_relink'`. Entri ini merekam keterhubungan kunci dokumen lama (`old_value`) ke kunci dokumen baru (`new_value`).
   - Perilaku ini telah didokumentasikan pada `docs/IMAGE_CLASSIFICATION.md`.

7. **G-7 & G-8 (Pembersihan Artefak Log & Pengujian Nyata Streamlit):**
   - Berkas log mentah pengujian yang memuat artefak terminal shell telah dihapus dari pelacakan Git repositori.
   - Pengujian nyata `test_g8_app_test_mounts_three_tabs_and_panels` memverifikasi bahwa halaman `src/ui/pages/4_KMS.py` berhasil memuat modul dan merender ketiga tab antarmuka tanpa error.




