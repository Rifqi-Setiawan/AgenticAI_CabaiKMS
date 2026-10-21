# CABAI-KMS — Akuisisi Data Multimodal

Prototipe penelitian **Adaptive Knowledge Acquisition berbasis Agentic AI** untuk mengubah spreadsheet karakterisasi cabai dan foto tanaman dari Google Drive menjadi workbook Excel berstruktur kanonik.

Dokumentasi diperbarui **23 September 2026**, berdasarkan implementasi di repositori, bukan hanya rancangan proposal.

## Kondisi proyek saat ini

- Pipeline Streamlit sudah menghubungkan parsing Excel, pencarian kandidat berbasis embedding, pemetaan atribut dengan LLM, normalisasi deterministik, klasifikasi citra opsional, dan ekspor `.xlsx`.
- Kolom varietas keluaran berasal dari input; baris karakter berasal dari `data/canonical/template_kanonik.xlsx`.
- LangGraph adalah koordinator runtime nyata: ingestion deterministik, schema matching/tabular, routing Drive, vision, lalu finalization. Checkpoint SQLite memakai `run_id` sebagai thread ID.
- Halaman **Hasil** menyediakan review untuk run aktif: approve usulan non-NULL, revise ke `canonical_key` aktif, atau `NO_MATCH`. Setelah seluruh item selesai, koreksi diterapkan deterministik dari output asli tanpa mengulang retrieval, LLM/reranker, verifier, atau vision; unduhan asli tetap tersedia dan event JSONL tetap append-only.
- UI hanya menerima `.xlsx`, menjalankan preflight lokal, dan menyediakan pilihan worksheet untuk workbook multi-sheet.
- Kontrol gambar dibatasi 1–20 (default 5). Ringkasan run, selective acceptance, review, hasil vision, unduhan, serta status tahap disajikan tanpa membuat jalur eksekusi selain LangGraph.
- Kampanye evaluasi lanjutan masih ditunda. Evaluasi otomatis Macro-F1 belum diimplementasikan; yang tersedia adalah infrastruktur ekspor tabel untuk penilaian manual.

## Mulai menjalankan

Jalankan dari direktori akar proyek menggunakan PowerShell. Jika `.venv` sudah tersedia dan berfungsi, lewati pembuatan environment.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
.\.venv\Scripts\python.exe -m streamlit run src/ui/app.py
```

## Provider 9Router (default)

CABAI-KMS terhubung ke endpoint OpenAI-compatible 9Router. Endpoint dapat berupa instance lokal (`http://127.0.0.1:20128/v1`) atau VPS ber-HTTPS (`https://domain-9router.example/v1`). Salin `.env.example` menjadi `.env` tanpa menimpa berkas yang sudah ada, lalu isi `NINEROUTER_BASE_URL` dan `NINEROUTER_API_KEY`; `.env` sudah diabaikan Git dan key tidak boleh di-commit.

Agent teks memakai `ag/gemini-3.8-flash-medium`, sedangkan agent vision untuk klasifikasi memakai `ag/gemini-3.8-flash-high`. Akun Antigravity, kuota, refresh autentikasi, dan account fallback sepenuhnya dikelola 9Router. CABAI-KMS melakukan satu panggilan vision tervalidasi: secondary consensus dinonaktifkan karena beberapa akun untuk model yang sama bukan consensus independen. Endpoint 9Router harus dapat dijangkau sebelum pipeline dimulai.

Model teks tidak dipanggil untuk semua kolom. Exact label/alias diselesaikan secara deterministik; hanya atribut unresolved yang melewati retrieval embedding dan reranker. Model vision hanya dipanggil bila folder Drive diberikan dan gambar ditemukan. Peta lengkap setiap flow, stack, logika, dan titik pemakaian model ada di [Tech Stack dan Alur Fitur](docs/TECH_STACK_AND_FLOWS.md).

Periksa koneksi dan daftar model dari PowerShell tanpa menyimpan key ke skrip:

```powershell
$env:NINEROUTER_API_KEY = Read-Host "Enter the 9Router API key"
Invoke-RestMethod `
  -Uri "https://domain-9router.example/v1/models" `
  -Headers @{ Authorization = "Bearer $env:NINEROUTER_API_KEY" }
```

Untuk rollback eksplisit, set `CABAI_KMS_TEXT_PROVIDER=legacy` dan `CABAI_KMS_VISION_PROVIDER=legacy`. Mode tersebut mempertahankan Groq → Ollama untuk teks, Gemini untuk vision, dan voter kedua OpenRouter → Ollama bila dipanggil secara eksplisit. Tidak ada fallback dari mode 9Router ke provider legacy. Bila selector tidak diisi, kode memilih `9router`; `.env.example` juga menyatakannya eksplisit.

Klasifikasi foto juga memerlukan kredensial service account Drive dan akses folder. Folder Drive boleh dikosongkan di UI untuk pemrosesan tabular saja.

Pemakaian pertama embedding dapat mengunduh model dari Hugging Face. Permintaan LLM/vision mengirim data ke provider dan dapat memakai kuota API. Detail dependensi, konfigurasi, dan batasan ada di panduan lengkap.

Rate limiting pada runner UI bersifat opsional. Isi `CABAI_KMS_TEXT_RPM` dan/atau `CABAI_KMS_VISION_RPM` dengan angka positif untuk membatasi attempt provider teks dan vision secara terpisah; nilai kosong menonaktifkannya. Batas ini bekerja pada boundary attempt aplikasi—termasuk retry—bukan sebagai jaminan atas setiap request HTTP tersembunyi di dalam SDK provider.

Kegagalan provider diklasifikasikan sebelum retry: timeout/koneksi, status 429,
dan status 5xx dapat diulang; konfigurasi/autentikasi/request permanen gagal cepat.
Default maksimum yang terlihat aplikasi adalah tiga attempt untuk kegagalan transien,
satu attempt untuk kegagalan non-retryable, atau tiga pemanggilan verifier kontrak (satu awal +
dua revisi) untuk output terstruktur yang invalid. Repair internal Instructor dan
fallback Groq → Ollama hanya berlaku pada legacy mode. OpenAI SDK memakai `max_retries=0`
untuk 9Router; repair Instructor tetap dibedakan dari retry transport aplikasi. Catatan normalisasi dan
alasan vision tidak ditulis tersedia pada hasil/trace. Resume dari checkpoint setelah
schema/tabular tidak mengulang pemanggilan schema-matching yang sudah selesai; replay
human-review tetap merupakan alur deterministik terpisah.

## Pengujian lokal

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m "not indexing and not llm_fallback_live and not ninerouter_live"
```

Perintah ini mengecualikan tes embedding dan koneksi fallback live; keberhasilannya bukan bukti API eksternal atau akurasi model sudah terverifikasi.

Setelah `NINEROUTER_API_KEY` diisi dan 9Router aktif, jalankan preflight live yang memeriksa reachability, `/v1/models`, structured text, dan citra PNG minimal nyata:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m ninerouter_live
```

Alternatif developer-facing yang menampilkan diagnostik tersanitasi dan mengembalikan exit code non-zero ketika gagal:

```powershell
.\.venv\Scripts\python.exe -B -m scripts.ninerouter_preflight
```

## Arsitektur Dokumen JSONB & Penyimpanan Pengetahuan (KMS V2)

KMS mengimplementasikan model penyimpanan dokumen pengetahuan berbasis **JSONB** (`kms.knowledge_documents`) menggunakan kontrak `KnowledgeDocument`:
- **Identitas Berpasangan**: Dokumen diidentifikasi oleh pasangan varietas tanaman dan habitat administratif teresolusi (`variety_id:habitat_id`), bukan varietas semata. Resolusi **habitat administratif** diturunkan dari hierarki wilayah administratif desa (`province`, `regency`, `district`, `village`) secara deterministik tanpa terpengaruh elevasi atau pH tanah.
- **Siklus Hidup Staging & Commit Transaksional**: Perubahan diproses melalui siklus hidup **staging** (`POST /runs/v2/stage`) dan diakhiri dengan **commit** transaksional all-or-nothing (`POST /runs/v2/{id}/commit`) setelah seluruh item review terselesaikan.
- **Migrasi Data Legacy & Kebijakan Retensi**: Migrasi dari skema relasional lama diatur melalui panduan operasional di [`docs/KMS_JSONB_MIGRATION.md`](docs/KMS_JSONB_MIGRATION.md). Data historis tanpa metadata habitat administratif dialihkan ke antrean **karantina** (*quarantine*). Tabel historis legacy dilindungi oleh kebijakan **retensi** transisi minimal 30 hari tanpa perintah purge otomatis di kode produk.
- **Status Aktivasi Konfigurasi**: Fitur penyimpanan dokumen JSONB dikendalikan oleh flag konfigurasi `kms_enabled` (atau variabel lingkungan `CABAI_KMS_ENABLED`). Secara default di lingkungan produksi, flag ini bernilai `false` (**nonaktif** / disabled) hingga seluruh gerbang pengujian formal (Gate 4) disetujui, memastikan kapabilitas yang telah teruji tidak diklaim aktif di produksi secara prematur.

## Peta dokumentasi

| Dokumen | Isi |
|---|---|
| [Tech stack dan alur fitur](docs/TECH_STACK_AND_FLOWS.md) | Peta end-to-end setiap fitur, logika keputusan, komponen deterministik, embedding, serta LLM/model vision yang dipakai pada setiap step |
| [Panduan lengkap proyek](docs/PROJECT_GUIDE.md) | Status implementasi, arsitektur, struktur file, kontrak data, alur, konfigurasi, penggunaan, testing, keterbatasan, dan pemeliharaan |
| [Panduan migrasi dokumen JSONB](docs/KMS_JSONB_MIGRATION.md) | Panduan operasional migrasi data legacy ke dokumen JSONB, akuntansi rekonsiliasi, karantina data tanpa habitat, dan kebijakan retensi 30 hari |
| [Runbook demo](docs/DEMO_RUNBOOK.md) | Checklist persiapan, alur demo langsung, dan fallback kegagalan |
| [Penyiapan Google Drive](docs/DRIVE_SETUP.md) | Langkah service account dan akses folder |
| [Keputusan desain](docs/DESIGN_DECISIONS.md) | Keputusan dan alasan; dibedakan dari implementasi yang sudah tersedia |
| [Profiling data](docs/PROFILING.md) | Catatan historis bentuk template dan contoh input |
| [Konvensi kontribusi](CLAUDE.md) | Ringkasan aturan proyek untuk kontributor/asisten |

Jangan hapus template, sampel, label review, atau kredensial hanya karena tidak diimpor langsung oleh Python. File tersebut merupakan aset atau konfigurasi proyek.
