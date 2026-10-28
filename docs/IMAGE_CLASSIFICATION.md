# Klasifikasi Citra Tanaman, Fusi Tiga Sinyal, dan Antrean Kandidat (KMS V2)

**Tanggal:** 28 Oktober 2026  
**Status:** Implementasi Aktif (Ronde 3)  
**Dokumen Terkait:** [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md) (D10–D13), [PROJECT_GUIDE.md](PROJECT_GUIDE.md)

---

## 1. Arsitektur Tiga Sinyal (Three-Way Signal Alignment)

Proses penautan foto Google Drive ke varietas tanaman dan dokumen pengetahuan mengevaluasi tiga sinyal independen:

1. **Sinyal 1 (Nama File & Caption):**
   - Diekstrak melalui `extract_photo_context_signal()`.
   - Mendeteksi bagian organ tanaman (`habitus`, `daun`, `batang`, `bunga`, `buah`, `biji`) berdasarkan kata kunci morfologi.
   - Menyaring stop-words non-diskriminatif (`cabai`, `cabe`, `chili`, `tanaman`, `foto`, `sample`, dll).

2. **Sinyal 2 (Registri Varietas Dinamis — `VarietyRegistry`):**
   - Menggabungkan varietas yang terdeteksi pada spreadsheet aktif dan varietas terdaftar pada database pengetahuan (`kms.knowledge_documents`).
   - Menyediakan pencocokan deterministik berbasis nama kanonik, alias daerah, dan token morfologi.

3. **Sinyal 3 (Inferensi Model Visi Multimodal):**
   - Menghasilkan `VisionClassificationResult` dengan status klasifikasi:
     * `KNOWN`: Varietas dikenali dengan keyakinan visual tinggi.
     * `OTHER`: Varietas baru yang tidak cocok dengan daftar opsi yang dievaluasi.
     * `UNCERTAIN`: Kualitas citra tidak memadai atau model ragu.

---

## 2. Aturan Fusi Sinyal (`fuse_photo_signals`)

Keputusan klasifikasi foto dikendalikan oleh fungsi deterministik `fuse_photo_signals()` dengan hierarki ketat:
> **Prinsip Utama: Sinyal visual model citra selalu menang atas nama file (*visual result wins over filename*). Bila terjadi konflik antar-sinyal, proses dialihkan ke kurasi manusia dan tidak pernah ditulis otomatis.**

Hasil evaluasi fusi sinyal memetakan citra ke salah satu dari empat aksi:

- **`AUTO_LINK`**:
  * Syarat: Status visual `KNOWN`, keyakinan $\ge 0.85$, varietas terdaftar pada registri, dan nama file tidak bertentangan.
  * Tindakan: Tautan foto ditulis otomatis ke sel worksheet kanonik.
- **`REVIEW_MISMATCH`**:
  * Syarat: Nama file bertentangan dengan bukti visual (contoh: nama file "cabai_rawit.jpg" namun model mendeteksi Cabai Keriting), ATAU status `KNOWN` namun varietas berada di luar registri aktif.
  * Tindakan: Membentuk item review pemblokir `PHOTO_VARIETY_MISMATCH` untuk diputuskan kurator.
- **`CANDIDATE`**:
  * Syarat: Status visual `OTHER` dengan keyakinan $\ge 0.80$, dan nama file tidak mengklaim varietas terdaftar yang bertentangan.
  * Tindakan: Citra dialihkan ke Antrean Kandidat (`kms.image_candidates`) tanpa menulis ke worksheet dan tanpa membuat dokumen prematur.
- **`REVIEW_UNCERTAIN`**:
  * Syarat: Status visual `UNCERTAIN` atau keyakinan model berada di bawah ambang batas ($< 0.85$ untuk KNOWN, $< 0.80$ untuk OTHER).
  * Tindakan: Membentuk item review kurasi `PHOTO_VARIETY_MISMATCH` (tidak pernah diangkat sebagai kandidat).

---

## 3. Antrean Kandidat Varietas Baru (`kms.image_candidates`) & Migrasi 0004

Citra yang berstatus `CANDIDATE` dicatat secara persisten pada tabel `kms.image_candidates` (migrasi aditif `0004`):

```sql
CREATE TABLE kms.image_candidates (
  candidate_id text PRIMARY KEY,
  asset_id text UNIQUE NOT NULL REFERENCES kms.media_assets(id),
  run_id text NOT NULL,
  source_filename text NOT NULL,
  original_sha256 text NOT NULL,
  organ_part text NOT NULL,
  suggested_name text,
  visual_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  confidence numeric(5,4) NOT NULL,
  status text NOT NULL DEFAULT 'CANDIDATE',
  resolution jsonb,
  decided_by text,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
```

### Tiga Aksi Resolusi Kandidat:
1. **`PROMOTE`**:
   - Mengangkat kandidat menjadi dokumen varietas baru (`KnowledgeDocument`).
   - Wajib menyertakan nama varietas baru (`new_variety_name`) dan alasan kurasi ($\ge 10$ karakter).
   - **Dukungan Habitat Belum Diketahui (`habitat_unknown` - Keputusan D11):** Bila habitat tidak disertakan, dokumen menggunakan identitas sentinel `habitat_unknown` dan diberi flag `habitat_unknown: true`. Dokumen ini otomatis masuk daftar antrean *"Dokumen Perlu Habitat"*.
2. **`MERGE`**:
   - Menautkan citra kandidat ke dokumen varietas dan habitat yang telah terdaftar (`media_refs`).
   - Membutuhkan `target_doc_key` atau pasangan `(variety_id, habitat_id)`.
3. **`DISCARD`**:
   - Menolak citra secara permanen. Rekaman `original_sha256` dicatat pada tabel `kms.discarded_images`.
   - Pipeline masa depan secara otomatis melewati citra yang pernah dibuang tanpa memanggil inferensi model ulang.

---

## 4. Rekonsiliasi Dokumen `habitat_unknown` (`SET_HABITAT`)

Dokumen berstatus `habitat_unknown: true` dapat direkonsiliasi oleh kurator setelah data lokasi lapangan definitif tersedia:
- Endpoint: `POST /documents/{doc_key}/habitat`
- Aksi: Memindahkan atau menggabungkan dokumen ke kunci `variety_id:habitat_id` yang sebenarnya dalam satu transaksi atomik. Seluruh atribut pengukuran dan referensi media dipindahkan tanpa kehilangan data.

---

## 5. Harness Evaluasi Model Visi (`scripts/eval_vision.py`)

Kinerja model visi dievaluasi menggunakan skrip evaluasi `scripts/eval_vision.py` dan manifest acuan `docs/eval/vision_manifest_example.csv`:

### Metrik yang Dihitung:
- **Top-1 Accuracy**: Akurasi klasifikasi varietas yang dikenali (`KNOWN`).
- **Macro-F1**: Rata-rata harmonik presisi dan recall per kelas varietas.
- **Recall OTHER**: Proporsi varietas baru yang berhasil diarahkan ke antrean `CANDIDATE`.
- **Candidate Precision**: Proporsi item pada antrean kandidat yang benar-benar merupakan varietas baru.
- **Review Rate**: Tingkat rujukan citra ke peninjauan manusia (`REVIEW_MISMATCH`, `REVIEW_UNCERTAIN`, `CANDIDATE`).
- **Threshold Sweep**: Analisis sensitivitas ambang keyakinan (rentang $0.50$ s.d. $0.95$ dengan interval $0.05$).

### Menjalankan Evaluasi:
```bash
# Mode offline menggunakan prediksi sintetis deterministik
python scripts/eval_vision.py --manifest docs/eval/vision_manifest_example.csv --output-dir data/eval_output --offline-mock
```
Output evaluasi menghasilkan berkas ringkasan markdown `eval_summary.md` dan tabel data sweep `sweep_results.csv`.
