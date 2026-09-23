# Tech Stack dan Alur Fitur CABAI-KMS

**Audit implementasi: 23 September 2026.** Dokumen ini mengikuti jalur kode yang aktif saat ini. Ia membedakan model generatif, model embedding, dan proses deterministik agar istilah "AI" tidak dipakai untuk semua tahap.

## Ringkasan runtime default

Runtime yang dipakai UI saat ini adalah:

| Bagian | Default aktif |
|---|---|
| Antarmuka | Streamlit, tiga halaman: Input, Progres, Hasil |
| Orkestrasi | LangGraph dengan checkpoint SQLite |
| Parser spreadsheet | `openpyxl`; `pandas` untuk tabel hasil |
| Backend ingestion | `legacy` |
| Backend retrieval | ChromaDB HNSW cosine |
| Model embedding | `paraphrase-multilingual-MiniLM-L12-v2` |
| Gateway model generatif | 9Router melalui API OpenAI-compatible |
| Model teks | `ag/gemini-3.8-flash-medium` |
| Model vision | `ag/gemini-3.8-flash-high` |
| Output terstruktur | Instructor + Pydantic |
| Akses citra | Google Drive API dengan service account read-only |
| Reliability | Tenacity, aiolimiter, verifier deterministik, dan trace tersanitasi |

9Router adalah gateway, bukan model. Aplikasi meminta ID model tertentu kepada 9Router; pemilihan akun Antigravity, kuota, dan pergantian akun ditangani oleh 9Router di luar aplikasi.

## Alur end-to-end

```text
Upload .xlsx
  -> preflight dan pilihan sheet/format
  -> LangGraph: source_ingestion
       -> parser legacy (default)
       -> atau profiler -> LLM struktur -> verifier -> parity gate (opt-in)
  -> LangGraph: schema_matching_tabular
       -> deteksi kolom varietas dengan embedding
       -> exact-name/alias resolution
       -> bila belum match: retrieval embedding dua-view
       -> LLM reranker memilih satu kandidat atau NULL
       -> verifier + selective acceptance
       -> normalisasi nilai + penulisan workbook
  -> bila folder Drive diisi: drive_crawler
  -> bila foto ditemukan: vision_classification
       -> model vision -> KNOWN/OTHER/UNCERTAIN
       -> hanya KNOWN yang memenuhi syarat ditulis sebagai URL
  -> finalization
  -> halaman Hasil
       -> review manusia dan replay deterministik tanpa model
```

## Peta fitur, tech stack, dan logika

| Flow/fitur | Tech stack dan modul utama | Logika yang dijalankan | AI/model yang dipakai |
|---|---|---|---|
| Upload dan preflight | Streamlit, `openpyxl`, `src/ui/app.py`, `src/ui/demo_support.py` | Menerima `.xlsx`, memastikan workbook dapat dibaca, menampilkan daftar worksheet, format, jumlah header, dan opsi Drive. Tidak memeriksa kesehatan jaringan provider. | Tidak ada |
| Orkestrasi | LangGraph, `src/orchestrator/graph.py` | Menjalankan node `source_ingestion -> schema_matching_tabular -> drive_crawler? -> vision_classification? -> finalization`. Node bertanda `?` dilewati bila tidak diperlukan. | Tidak ada pada orkestratornya |
| Checkpoint dan resume | LangGraph SQLite saver, `sqlite3` | Menyimpan state antarnode memakai `run_id` sebagai thread ID. Resume menolak sumber atau konfigurasi yang fingerprint-nya berbeda. | Tidak ada |
| Parsing default | `openpyxl`, `src/agents/schema_matching/source_parsing.py`, `src/ingestion/runtime_source.py` | Mendukung row-oriented dengan 1/2 header dan transposed dengan anchor `Karakter`. Menjaga posisi nilai terhadap varietas. | Tidak ada |
| Pemahaman struktur opt-in | Profiler `openpyxl`, Pydantic, `src/ingestion/*` | `source-ir-gated` atau shadow membangun fakta sel, meminta proposal struktur, memverifikasinya secara geometrik, lalu mempromosikan Source IR hanya jika parity terhadap parser legacy tepat `MATCH`. | Model teks 9Router; hanya ketika backend/flag ini diaktifkan |
| Deteksi kolom varietas | sentence-transformers, cosine similarity, `anchor.py` | Membandingkan embedding nama header dengan frasa konsep varietas; kandidat terbaik harus melewati threshold `0.7`. | Model embedding; bukan LLM generatif |
| Memuat skema kanonik | `openpyxl`, YAML, Pydantic, `canonical.py` | Membaca baris kanonik dari template, domain, stable `canonical_key`, contoh nilai, dan alias. | Tidak ada |
| Exact-name resolution | Normalisasi string Python, `exact_match.py` | Label atau alias yang sama setelah trim, normalisasi whitespace, dan casefold serta hanya dimiliki satu row langsung dipetakan dengan confidence `1.0`. Retrieval dan LLM dilewati. Konflik alias masuk jalur semantik. | Tidak ada |
| Retrieval kandidat | sentence-transformers, ChromaDB; opsi exact memakai NumPy | Mengambil kandidat berdasarkan cosine distance. Backend default adalah ANN Chroma; backend `exact` menghitung cosine terhadap semua row di memori. | Model embedding; bukan LLM generatif |
| Header-only retrieval fallback | `pipeline_runner._retrieve_with_header_fallback()` | Query utama memakai nama, konteks, contoh nilai, dan tipe. Bila contoh nilai tersedia dan top-k lengkap, query kedua memakai header/konteks tanpa contoh nilai dengan `k=10`. Kandidat digabung per row memakai distance terbaik lalu diurutkan kembali. | Model embedding; bukan LLM generatif |
| Reranking schema | Instructor, Pydantic `SchemaMapping`, OpenAI SDK, `reranking.py`, `providers.py` | Hanya menerima kandidat hasil retrieval, lalu memilih satu row atau `NULL`, confidence, reasoning, dan flag normalisasi. Output divalidasi terhadap kontrak Pydantic. | `ag/gemini-3.8-flash-medium` via 9Router |
| Mapping verifier | Python deterministik, `mapping_verifier.py` | Memeriksa target berada di skema/candidate set, candidate unik dan terurut, format konsisten, serta invariants exact-name. Hard violation menjadi `REJECT`/`NO_WRITE`; warning tidak otomatis membatalkan mapping. | Tidak ada |
| Selective acceptance | `review_queue.py` | `AUTO_ACCEPT` hanya untuk mapping non-NULL, confidence minimal `0.6`, dan tanpa `error_trace`. `NULL` atau confidence rendah menjadi `REVIEW`; mapping hilang/hard reject menjadi `NO_WRITE`. Telemetri sukses di `provider_trace` tidak memicu review. | Tidak ada |
| Normalisasi nilai | Regex dan rule Python, `normalize.py` | Merapikan token kosong, desimal koma, dash rentang, separator multi-value, whitespace, dan exact vocabulary matching. Nilai yang tidak aman dikonversi dipertahankan dengan catatan. | Tidak ada |
| Penulisan workbook | `openpyxl`, `output_builder.py` | Menyalin template, membuat kolom varietas input, dan hanya menulis mapping `AUTO_ACCEPT`. Beberapa observasi untuk varietas/atribut sama digabung dengan `; `. | Tidak ada |
| Drive crawler | Google Drive API v3, service account, `drive_crawler.py` | Melakukan listing flat pada anak langsung folder, pagination, dan filter MIME `image/*`; tidak menelusuri subfolder. | Tidak ada |
| Klasifikasi citra | Instructor, Pydantic `VisionResult`, OpenAI-compatible multimodal request | Mengirim bytes foto, nama file, dan deskripsi varietas dari template. Nama file hanya petunjuk. Model mengembalikan bagian tanaman, varietas, status, confidence, dan bukti visual. | `ag/gemini-3.8-flash-high` via 9Router |
| Penulisan hasil vision | `tabular_update.py` | URL Drive ditulis hanya untuk status `KNOWN`, varietas yang ada di output, dan row `Gambar Daun/Batang/Buah/Bunga` yang ditemukan. `OTHER`, `UNCERTAIN`, atau hasil gagal tidak ditulis. | Tidak ada setelah hasil model diterima |
| Manual review | Streamlit, JSONL append-only, `review_queue.py`, `3_Hasil.py` | Reviewer dapat approve, revise ke `canonical_key`, atau `NO_MATCH`. Koreksi direplay dari workbook asli setelah semua item selesai. | Tidak ada; retrieval, LLM, verifier, dan vision tidak diulang |
| Evaluasi | pandas/openpyxl, kontrak anotasi dan kalibrasi di `eval/` dan `src/schema/` | Membuat tabel untuk label manusia, stable mapping ID, validasi anotasi, split workbook, dan analisis selective risk. Belum menghasilkan klaim akurasi final. | Pipeline pembentuk prediksi dapat memakai LLM; penilaian gold harus dilakukan manusia |

## Detail schema matching

Urutan keputusan untuk satu atribut sumber adalah:

1. Bentuk `SourceAttributeProfile` dari nama atribut, parent header, maksimal 10 contoh nilai, dan tipe data heuristik.
2. Coba exact-name terhadap label dan alias kanonik.
3. Jika exact match unik ditemukan, hasil langsung masuk verifier tanpa embedding retrieval atau LLM.
4. Jika tidak, siapkan indeks secara lazy dan jalankan retrieval profil lengkap.
5. Untuk atribut yang memiliki contoh nilai, jalankan juga retrieval header-only. Ini mencegah angka atau kategori generik mendominasi makna header, misalnya banyak kolom panjang terlihat mirip hanya karena seluruh nilainya numerik.
6. Gabungkan kandidat dari kedua query. Untuk canonical row yang muncul dua kali, simpan cosine distance yang lebih kecil. Urutkan ascending sebelum diberikan kepada reranker dan verifier.
7. Model teks memilih salah satu kandidat atau `NULL`; model tidak boleh memilih row di luar candidate set.
8. Verifier memeriksa hard invariant. Acceptance layer kemudian menentukan `AUTO_ACCEPT`, `REVIEW`, atau `NO_WRITE`.
9. Hanya `AUTO_ACCEPT` melewati batas mutasi ke normalisasi dan workbook kanonik.

Secara ringkas:

```text
exact unique
  -> mapping confidence 1.0
  -> verifier

tidak exact / exact ambigu
  -> retrieval profil lengkap + header-only fallback
  -> gabung dan urutkan kandidat
  -> LLM reranker
  -> verifier

hard invariant gagal                   -> NO_WRITE
target NULL / confidence < 0.6 / error -> REVIEW
selain itu                             -> AUTO_ACCEPT -> normalize -> write
```

`verifier=PASS` berarti kontrak teknis konsisten, bukan jaminan makna mapping pasti benar. Confidence model juga belum dikalibrasi sebagai probabilitas kebenaran.

### Perilaku row kosong

Pada format row-oriented, parser mempertahankan semua posisi observasi agar kolom tetap sejajar:

- baris yang seluruh selnya kosong diperbolehkan dan tidak menghasilkan kontribusi nilai;
- beberapa baris kosong berurutan juga aman;
- baris dengan varietas kosong tetapi kolom lain berisi data ditolak, karena sistem tidak dapat menentukan pemilik observasinya;
- nilai atribut kosong pada baris dengan varietas valid hanya dilewati untuk atribut tersebut;
- observasi berulang dengan nama varietas sama digabung menggunakan `; `, bukan dirata-ratakan.

Pada format transposed, baris tanpa label atribut di kolom pertama dilewati. Posisi kolom varietas tetap mengikuti header setelah `Karakter`.

## Model yang dipakai dan pada step apa

### Runtime 9Router yang aktif

| Model | Jenis | Dipakai pada step | Kapan tidak dipanggil |
|---|---|---|---|
| `ag/gemini-3.8-flash-medium` | LLM teks | Reranking atribut yang tidak selesai melalui exact-name; juga Structure Understanding bila `source-ir-gated` atau structure shadow diaktifkan | Exact-name unik; parser legacy biasa; normalisasi; verifier; review/replay |
| `ag/gemini-3.8-flash-high` | Model vision/multimodal | Klasifikasi setiap foto yang ditemukan Drive | Folder Drive kosong, tidak ada gambar, atau tahap vision dilewati |
| `paraphrase-multilingual-MiniLM-L12-v2` | Model embedding lokal | Deteksi anchor varietas, embedding skema kanonik, retrieval profil lengkap, dan retrieval header-only | Bukan model generatif; tidak menghasilkan keputusan akhir mapping |

Mode 9Router tidak otomatis jatuh ke provider legacy. Bila request 9Router gagal, reliability layer mengklasifikasikan error, melakukan retry hanya untuk kegagalan transien, lalu fail closed ke review/no-write sesuai konteks.

### Provider legacy yang masih tersedia untuk rollback eksplisit

| Jalur legacy | Model | Peran |
|---|---|---|
| Text primary | Groq `openai/gpt-oss-120b` | Structure Understanding dan schema reranking |
| Text fallback | Ollama `llama3.1:8b` | Dipanggil bila jalur Groq legacy gagal |
| Vision primary | Gemini, default `gemini-flash-latest` | Klasifikasi citra |
| Vision second voter, opsional | OpenRouter `qwen/qwen2.5-vl-72b-instruct` | Consensus hanya bila diminta melalui API Python dalam mode legacy |
| Vision second-voter fallback | Ollama `qwen2.5-vl:7b` | Fallback untuk second voter OpenRouter |

Legacy hanya aktif bila `CABAI_KMS_TEXT_PROVIDER=legacy` dan/atau `CABAI_KMS_VISION_PROVIDER=legacy` dipilih eksplisit. UI default tidak meminta consensus. Dalam mode 9Router, consensus selalu dinonaktifkan karena memanggil model yang sama melalui akun berbeda bukan voting model independen.

## Data yang keluar dari mesin

| Tujuan | Data yang dikirim |
|---|---|
| 9Router text | Nama atribut, konteks header, contoh nilai terbatas, tipe data, dan daftar kandidat kanonik; pada Structure Understanding opt-in, compact worksheet evidence dan range tambahan yang dibatasi |
| 9Router vision | Bytes citra, MIME type, nama file, serta deskripsi varietas yang dibaca dari template |
| Google Drive API | Kredensial service account pada proses autentikasi dan permintaan metadata/download file sesuai folder yang diberikan |

Model embedding berjalan melalui sentence-transformers pada runtime lokal setelah model tersedia di cache. Workbook penuh tidak dikirim ke reranker schema; model menerima profil per atribut dan kandidat yang sudah dibatasi. API key tidak disimpan dalam checkpoint LangGraph atau output workbook.

## Reliability dan observability

- OpenAI SDK untuk 9Router memakai `max_retries=0`; retry transport dikendalikan aplikasi.
- Tenacity mengulang timeout/koneksi, 408/409/429, dan 5xx hingga maksimum tiga attempt dengan exponential backoff. Error autentikasi, konfigurasi, model tidak ditemukan, atau request permanen berhenti cepat.
- Provider helper meneruskan `max_retries=2` kepada Instructor untuk repair output terstruktur. Di luar itu, verifier aplikasi dapat mengulang pemanggilan kontrak maksimal dua kali lagi setelah `ValidationError`. Keduanya berbeda dari retry transport.
- `CABAI_KMS_TEXT_RPM` dan `CABAI_KMS_VISION_RPM` mengaktifkan limiter attempt per proses; nilai kosong berarti tidak dibatasi oleh aplikasi.
- `provider_trace` menyimpan metadata tersanitasi seperti model, role, latency, success, dan failure kind. Ia tidak menyimpan API key atau payload penuh.
- `error_trace` menyimpan kondisi yang perlu perhatian, termasuk kegagalan provider, warning normalisasi, dan alasan vision tidak ditulis.

## Lokasi implementasi utama

| Kebutuhan | File utama |
|---|---|
| UI dan input | `src/ui/app.py`, `src/ui/pages/` |
| Integrasi pipeline tabular | `src/ui/pipeline_runner.py` |
| Graph dan checkpoint | `src/orchestrator/graph.py` |
| Parsing dan posisi data | `src/agents/schema_matching/source_parsing.py`, `src/ingestion/runtime_source.py` |
| Exact/retrieval/reranking | `src/agents/schema_matching/exact_match.py`, `retrieval.py`, `reranking.py` |
| Verifier dan acceptance | `src/agents/schema_matching/mapping_verifier.py`, `review_queue.py` |
| Provider 9Router/legacy | `src/llm/openai_compatible.py`, `providers.py`, `vision_providers.py` |
| Vision dan Drive | `src/agents/vision_classification.py`, `drive_crawler.py`, `tabular_update.py` |
| Normalisasi/output | `src/agents/schema_matching/normalize.py`, `src/ui/output_builder.py` |
| Kontrak data | `src/schema/contracts.py`, `src/schema/state.py` |

Untuk konfigurasi, batas input, cara menjalankan UI, review, evaluasi, dan troubleshooting, lanjutkan ke [PROJECT_GUIDE.md](PROJECT_GUIDE.md). Untuk operasi demo 9Router, lihat [DEMO_RUNBOOK.md](DEMO_RUNBOOK.md).
