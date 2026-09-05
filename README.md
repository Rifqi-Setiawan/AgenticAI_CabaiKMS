# CABAI-KMS — Akuisisi Data Multimodal

Prototipe penelitian **Adaptive Knowledge Acquisition berbasis Agentic AI** untuk mengubah spreadsheet karakterisasi cabai dan foto tanaman dari Google Drive menjadi workbook Excel berstruktur kanonik.

Dokumentasi diperbarui **3 September 2026**, berdasarkan implementasi di repositori, bukan hanya rancangan proposal.

## Kondisi proyek saat ini

- Pipeline Streamlit sudah menghubungkan parsing Excel, pencarian kandidat berbasis embedding, pemetaan atribut dengan LLM, normalisasi deterministik, klasifikasi citra opsional, dan ekspor `.xlsx`.
- Kolom varietas keluaran berasal dari input; baris karakter berasal dari `data/canonical/template_kanonik.xlsx`.
- Graf LangGraph masih **stub** untuk pengujian alur/checkpoint. Graf ini bukan pelaksana agen nyata di UI.
- Review queue tersedia melalui API Python, tetapi UI belum menyediakan persetujuan/koreksi atau penerapan ulang hasil review.
- CSV belum didukung parser walaupun ditawarkan uploader. Gunakan `.xlsx`.
- Evaluasi otomatis Macro-F1 belum diimplementasikan; yang tersedia adalah ekspor tabel untuk penilaian manual.

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

## Pengujian lokal

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m "not indexing and not llm_fallback_live"
```

Perintah ini mengecualikan tes embedding dan koneksi fallback live; keberhasilannya bukan bukti API eksternal atau akurasi model sudah terverifikasi.

## Peta dokumentasi

| Dokumen | Isi |
|---|---|
| [Panduan lengkap proyek](docs/PROJECT_GUIDE.md) | Status implementasi, arsitektur, struktur file, kontrak data, alur, konfigurasi, penggunaan, testing, keterbatasan, dan pemeliharaan |
| [Penyiapan Google Drive](docs/DRIVE_SETUP.md) | Langkah service account dan akses folder |
| [Keputusan desain](docs/DESIGN_DECISIONS.md) | Keputusan dan alasan; dibedakan dari implementasi yang sudah tersedia |
| [Profiling data](docs/PROFILING.md) | Catatan historis bentuk template dan contoh input |
| [Pertanyaan desain](docs/OPEN_QUESTIONS.md) | Riwayat keputusan dan pertanyaan yang ditunda |
| [Catatan verifikasi](docs/CHECKPOINTS.md) | Bukti pengujian terdahulu dan audit dokumentasi/pembersihan |
| [Konvensi kontribusi](CLAUDE.md) | Ringkasan aturan proyek untuk kontributor/asisten |

Jangan hapus template, sampel, label review, atau kredensial hanya karena tidak diimpor langsung oleh Python. File tersebut merupakan aset atau konfigurasi proyek.


.\.venv\Scripts\python.exe -m streamlit run src/ui/app.py