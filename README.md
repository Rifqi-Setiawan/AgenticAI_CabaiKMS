# CABAI-KMS — Akuisisi Data Multimodal

Prototipe penelitian **Adaptive Knowledge Acquisition berbasis Agentic AI** untuk mengubah spreadsheet karakterisasi cabai dan foto tanaman dari Google Drive menjadi workbook Excel berstruktur kanonik.

Dokumentasi diperbarui **9 September 2026**, berdasarkan implementasi di repositori, bukan hanya rancangan proposal.

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

Isi `GROQ_API_KEY` di `.env` untuk schema matching melalui Groq. Fallback teks memerlukan Ollama lokal dengan model yang sesuai. Klasifikasi foto memerlukan `GOOGLE_API_KEY`, kredensial service account Drive, dan akses folder. Folder Drive boleh dikosongkan di UI untuk pemrosesan tabular saja.

Pemakaian pertama embedding dapat mengunduh model dari Hugging Face. Permintaan LLM/vision mengirim data ke provider dan dapat memakai kuota API. Detail dependensi, konfigurasi, dan batasan ada di panduan lengkap.

Rate limiting pada runner UI bersifat opsional. Isi `CABAI_KMS_TEXT_RPM` dan/atau `CABAI_KMS_VISION_RPM` dengan angka positif untuk membatasi attempt provider teks dan vision secara terpisah; nilai kosong menonaktifkannya. Batas ini bekerja pada boundary attempt aplikasi—termasuk retry—bukan sebagai jaminan atas setiap request HTTP tersembunyi di dalam SDK provider.

Kegagalan provider diklasifikasikan sebelum retry: timeout/koneksi, status 429,
dan status 5xx dapat diulang; konfigurasi/autentikasi/request permanen gagal cepat.
Default maksimum yang terlihat aplikasi adalah tiga attempt untuk kegagalan transien,
satu attempt untuk kegagalan non-retryable, atau tiga pemanggilan kontrak (satu awal +
dua revisi) untuk output terstruktur yang invalid. Retry internal SDK/instructor dan
fallback Groq → Ollama berada di bawah batas observasi ini. Catatan normalisasi dan
alasan vision tidak ditulis tersedia pada hasil/trace. Resume dari checkpoint setelah
schema/tabular tidak mengulang pemanggilan schema-matching yang sudah selesai; replay
human-review tetap merupakan alur deterministik terpisah.

## Pengujian lokal

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m "not indexing and not llm_fallback_live"
```

Perintah ini mengecualikan tes embedding dan koneksi fallback live; keberhasilannya bukan bukti API eksternal atau akurasi model sudah terverifikasi.

## Peta dokumentasi

| Dokumen | Isi |
|---|---|
| [Panduan lengkap proyek](docs/PROJECT_GUIDE.md) | Status implementasi, arsitektur, struktur file, kontrak data, alur, konfigurasi, penggunaan, testing, keterbatasan, dan pemeliharaan |
| [Runbook demo](docs/DEMO_RUNBOOK.md) | Checklist persiapan, alur demo langsung, dan fallback kegagalan |
| [Penyiapan Google Drive](docs/DRIVE_SETUP.md) | Langkah service account dan akses folder |
| [Keputusan desain](docs/DESIGN_DECISIONS.md) | Keputusan dan alasan; dibedakan dari implementasi yang sudah tersedia |
| [Profiling data](docs/PROFILING.md) | Catatan historis bentuk template dan contoh input |
| [Pertanyaan desain](docs/OPEN_QUESTIONS.md) | Riwayat keputusan dan pertanyaan yang ditunda |
| [Catatan verifikasi](docs/CHECKPOINTS.md) | Bukti pengujian terdahulu dan audit dokumentasi/pembersihan |
| [Konvensi kontribusi](CLAUDE.md) | Ringkasan aturan proyek untuk kontributor/asisten |

Jangan hapus template, sampel, label review, atau kredensial hanya karena tidak diimpor langsung oleh Python. File tersebut merupakan aset atau konfigurasi proyek.


.\.venv\Scripts\python.exe -m streamlit run src/ui/app.py
