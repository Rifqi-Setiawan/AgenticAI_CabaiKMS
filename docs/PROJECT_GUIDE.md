# Panduan Lengkap CABAI-KMS Akuisisi

**Audit implementasi: 5 September 2026.** Dokumen ini menjelaskan apa yang benar-benar tersedia pada kode saat audit. Nama model dan nilai default di sini adalah konfigurasi kode, bukan jaminan ketersediaan layanan eksternal. Catatan eksperimen Juli 2026 tetap disimpan sebagai riwayat.

## Daftar isi

1. [Tujuan dan cakupan](#1-tujuan-dan-cakupan)
2. [Status implementasi](#2-status-implementasi)
3. [Arsitektur dan alur eksekusi](#3-arsitektur-dan-alur-eksekusi)
4. [Struktur repositori](#4-struktur-repositori)
5. [Input dan skema kanonik](#5-input-dan-skema-kanonik)
6. [Kontrak data dan hasil](#6-kontrak-data-dan-hasil)
7. [Instalasi dan konfigurasi](#7-instalasi-dan-konfigurasi)
8. [Penggunaan UI dan API Python](#8-penggunaan-ui-dan-api-python)
9. [Review dan evaluasi](#9-review-dan-evaluasi)
10. [Reliability dan checkpoint](#10-reliability-dan-checkpoint)
11. [Pengujian dan troubleshooting](#11-pengujian-dan-troubleshooting)
12. [Keterbatasan dan pekerjaan lanjutan](#12-keterbatasan-dan-pekerjaan-lanjutan)
13. [Pemeliharaan, keamanan, dan pembersihan](#13-pemeliharaan-keamanan-dan-pembersihan)

## 1. Tujuan dan cakupan

Data lapangan cabai dapat menggunakan nama atribut berbeda, susunan spreadsheet berbeda, nilai rentang/desimal tidak konsisten, serta foto tanaman tanpa pengelompokan bagian tanaman. Proyek ini membantu menyelaraskan data tersebut ke template kanonik untuk CABAI-KMS.

Masukan utama adalah workbook Excel; foto dari satu folder Google Drive bersifat opsional. Keluaran UI adalah workbook `hasil_akuisisi.xlsx`, tabel pemetaan, hasil klasifikasi citra, status agen, dan log proses.

Ini adalah **prototipe penelitian**, bukan sistem produksi, API backend, atau platform pengelolaan knowledge base lengkap. Normalisasi nilai saat ini menggunakan aturan Python; LLM melakukan pemetaan semantik atribut dan LVM melakukan interpretasi citra.

## 2. Status implementasi

| Komponen | Kondisi pada kode |
|---|---|
| Skema kanonik dan domain | Aktif; dibaca dari Excel dan YAML, jumlah baris dinamis |
| Parsing spreadsheet | Aktif untuk dua bentuk `.xlsx` dengan batasan struktur pada §5 |
| Workbook Structure Profiler | Tersedia secara standalone; deterministik, faktual, dan sparse-safe |
| Structure Understanding Agent | Tersedia secara standalone; evidence ringkas, output Pydantic, dan retry evidence terarah yang dibatasi; belum dipakai pipeline UI |
| Structure Verifier | Deterministik dan wajib lulus sebelum struktur boleh menjadi Source IR |
| Source ingestion | `legacy` tetap default; `legacy + shadow` hanya observasi; `source-ir-gated` dapat menjadi input produksi hanya setelah parity `MATCH` |
| Anchor varietas | Aktif, embedding header, ambang similarity `0.7` |
| Retrieval | Aktif, indeks baris kanonik ChromaDB; default top-k `8` |
| Reranking | Aktif, Groq dengan fallback Ollama; output Pydantic |
| Normalisasi | Aktif, deterministik; bukan ekstraksi/penalaran bebas oleh LLM |
| Google Drive | Aktif, service account read-only, daftar foto anak langsung folder |
| Vision | Aktif, Gemini; consensus dua model tersedia di API Python, tidak di UI |
| Penulisan Excel | Aktif, varietas dari input, URL citra untuk hasil `KNOWN` |
| Retry dan validasi ulang | Dipakai runner UI melalui reliability wrappers |
| Rate limiter | Implementasi dan tes tersedia, tetapi runner UI tidak memasok instance limiter |
| Manual review | Queue JSONL dan API approve/revise tersedia; belum menjadi alur koreksi UI |
| LangGraph | Node stub dengan checkpoint/resume SQLite; agen nyata belum terpasang di node |
| UI | Tiga halaman Streamlit: Input, Progres, Hasil |
| Evaluasi | Harness ekspor untuk review manual; belum ada perhitungan Macro-F1 |

**Implikasi:** status “selesai” menunjukkan eksekusi selesai, bukan seluruh data sudah benar atau telah disetujui manusia. Baca detail pemetaan dan log sebelum menggunakan hasil untuk penelitian.

### Status Phase 4: pemahaman struktur standalone

Alur baru `WorkbookProfile -> StructureProposal -> VerifiedStructure -> SourceIR`
telah tersedia untuk pengujian independen. Profiler hanya mencatat observasi fisik.
Agent menerima view evidence yang dibatasi, bukan dump seluruh profil, dan dapat
meminta maksimal dua putaran range kecil yang divalidasi. Evidence terarah bersifat
kumulatif, memakai anggaran global 1.500 posisi sel, dan permintaan range normalisasi
yang sama tidak boleh diulang. Proposal model berstatus
`RESOLVED` tetap tidak dipercaya sampai verifier geometrik deterministik lulus.
`AMBIGUOUS` dan `UNSUPPORTED` adalah hasil abstain yang sah dan tidak menghasilkan
Source IR.

Source IR mempertahankan koordinat header dan nilai, termasuk posisi kosong, tanpa
normalisasi atau schema matching. Fitur ini sengaja belum mengganti parser lama dan
belum dipasang ke LangGraph. `run_pipeline_ui()` dapat menjalankannya hanya sebagai
shadow comparison melalui `enable_structure_shadow=True`; default tetap `False`.
Hasil shadow tidak pernah mengganti atribut, posisi varietas, mapping, atau workbook
dari parser legacy. Karena itu, dukungan spreadsheet berantakan belum boleh dianggap
aktif pada UI produksi.
Pada setiap `SourceValueIR`, `coordinate` adalah posisi logis dalam geometri tabel,
sedangkan `source_coordinate` adalah sel fisik yang menyimpan nilai atau anchor
kiri-atas merge. Posisi kosong memiliki `source_coordinate = None`.

### Jalur produksi dan shadow

Jalur produksi tetap `legacy parser -> anchor/entity -> retrieval -> reranking ->
acceptance -> normalization -> canonical output`. Bila flag shadow diaktifkan, satu
jalur observasi terisolasi menjalankan `WorkbookProfile -> Structure Understanding ->
Verifier -> Source IR -> compatibility adapter -> parity report`. Status `MATCH`
hanya berarti keluaran logisnya setara dengan parser legacy, bukan bukti bahwa keduanya
benar terhadap ground truth. Status berbeda, abstain, atau gagal hanya dicatat dan
tidak mengubah hasil produksi.

### Tiga status backend ingestion

1. `legacy` adalah backend produksi default. Tidak ada profiling struktur, parity,
   atau biaya model struktur kecuali shadow diminta terpisah.
2. `legacy + shadow` diaktifkan dengan `enable_structure_shadow=True`. Parser legacy
   tetap menjadi sumber produksi; jalur baru hanya menghasilkan laporan.
3. `source-ir-gated` adalah opt-in eksplisit melalui `source_backend`. Pipeline
   menyiapkan referensi legacy, membangun satu kandidat Source IR, dan mempromosikan
   kandidat itu hanya bila laporan parity tepat `MATCH`. `DIFFERENT`, abstain,
   kegagalan verifier/model, serta legacy-fail/new-success berhenti sebelum indexing
   dan tidak menghasilkan output kanonik. Flag shadow yang redundan memakai laporan
   gate yang sama dan tidak menjalankan agen struktur dua kali.

Setelah promosi, pipeline memakai atribut runtime Source IR pada loop schema matching
yang sama. Prompt retrieval/reranking tetap hanya menerima nama atribut, konteks, dan
contoh nilai. Provenance write yang benar-benar diakui builder menyimpan
`source_cells` sebagai sel fisik nilai dan `source_header_cells` sebagai sel fisik
identitas header; backend legacy tetap memakai daftar koordinat kosong.

Bytes XLSX sengaja diserialisasi deterministik untuk reproduksibilitas pengujian.
Timestamp ZIP dan metadata `modified` dinormalisasi, sehingga metadata tersebut bukan
waktu ekspor aktual.

## 3. Arsitektur dan alur eksekusi

Lima lapisan utama adalah data/skema, ingestion, agen, orkestrasi/reliability, serta UI/evaluasi. `src/llm/` menyediakan akses provider lintas agen.

```text
Input .xlsx
  -> parser sesuai format pilihan pengguna
  -> identitas varietas (anchor / header transposed)
  -> indeks dan retrieval kandidat baris kanonik
  -> safe_rerank -> SchemaMapping -> normalisasi -> akumulasi nilai
  -> workbook berdasarkan salinan template
  -> [opsional] Drive -> download -> Gemini -> URL foto pada sel Gambar
  -> tabel preview + bytes Excel + log/status

Di akhir runner UI:
  -> graf LangGraph STUB -> SQLite -> debugger checkpoint
     (bukan rekaman/resume pemrosesan agen nyata di atas)
```

### Jalur aplikasi nyata

Fungsi `run_pipeline_ui()` di `src/ui/pipeline_runner.py` menjalankan proses secara sinkron:

1. Membaca sheet pilihan; secara default sheet pertama. UI tidak memiliki pilihan sheet.
2. Pada format row-oriented, mendeteksi kolom varietas dari embedding teks header saja. Pada transposed, memakai nama kolom setelah `Karakter`.
3. Memuat `CanonicalSchema` dan memastikan indeks Chroma tersedia.
4. Untuk setiap atribut non-anchor, membuat profil nama/konteks/contoh nilai, mengambil kandidat, lalu memanggil `safe_rerank()`.
5. Mapping melewati gerbang acceptance deterministik. Hanya `AUTO_ACCEPT` yang boleh dinormalisasi dan ditulis; `REVIEW` dan `NO_WRITE` tidak boleh mengubah workbook kanonik. Mapping `NULL`, target tidak valid, dan kegagalan lain berhenti sebagai `NO_WRITE`.
6. Menggabungkan nilai per varietas dengan pemisah `; `, lalu membangun workbook dari template. Sel referensi varietas lama dibersihkan pada salinan yang berada di memori, bukan file template asli.
7. Jika URL/ID Drive diberikan, mengambil metadata foto lalu memproses maksimal lima gambar secara default. Pembatasan dilakukan setelah listing, bukan membatasi jumlah metadata yang diminta dari Drive.
8. Membaca deskripsi varietas template sekali melalui `VisionSession`, mengunduh foto, dan memanggil `safe_classify_image()`.
9. Menulis URL Drive hanya jika status `KNOWN`, varietas ada di kolom output, dan baris bagian tanaman ditemukan. Tidak ada threshold confidence numerik tambahan di penulis sel.
10. Membaca kembali worksheet menjadi DataFrame, menyimpan workbook ke bytes, lalu menjalankan graf stub untuk debugger.

### Jalur evaluasi manual

`eval/review_schema_matching.py` memakai parser, anchor, retrieval, reranker, dan normalizer yang sama, tetapi tanpa wrapper reliability UI, tanpa foto, dan tanpa workbook kanonik akhir. Hasilnya tabel pemetaan untuk dinilai manusia, bukan laporan metrik otomatis.

## 4. Struktur repositori

```text
project/
├── README.md                    Pintu masuk dan cara cepat menjalankan
├── CLAUDE.md                    Ringkasan konvensi kontribusi
├── requirements.txt             Dependensi runtime dan pytest (belum dipin)
├── pyproject.toml               Konfigurasi pytest; bukan manifest paket lengkap
├── .env.example                Contoh konfigurasi tanpa rahasia
├── .gitignore
├── docs/                       Panduan, keputusan, profiling, riwayat audit
├── data/
│   ├── canonical/              template_kanonik.xlsx, input utama
│   ├── samples/                Tiga workbook contoh nyata/sintetis
│   ├── gold/                   Dua workbook review historis, dipertahankan
│   ├── review/                 Queue JSONL lokal, dibuat saat diperlukan
│   ├── .chroma/                Indeks embedding lokal
│   └── .checkpoints/           SQLite graf stub
├── src/
│   ├── schema/                 Skema, domain, alias, kontrak, shared state
│   ├── agents/
│   │   ├── schema_matching/    Parsing sampai review/normalisasi
│   │   ├── drive_crawler.py
│   │   ├── vision_classification.py
│   │   └── tabular_update.py
│   ├── llm/                    Provider teks dan vision
│   ├── orchestrator/           Graf stub dan checkpoint/resume
│   ├── reliability/            Retry, rate limiter, verifier, wrappers
│   └── ui/                     Aplikasi, runner, output builder, state
│       └── pages/              2_Progress.py dan 3_Hasil.py
├── eval/review_schema_matching.py
└── tests/                      Tes modul dan halaman Streamlit
```

`.venv/`, `.env`, dan `credentials.json` dapat tersedia secara lokal; bukan bagian source yang perlu dibagikan. File `__init__.py` kosong merupakan penanda paket dan tetap dipertahankan.

### Tanggung jawab modul

| Modul | Tanggung jawab |
|---|---|
| `schema/canonical.py` | Memuat label/contoh, lookup domain/alias, membuat ID dan hash template |
| `schema/contracts.py` | Validasi `SchemaMapping`, `VisionResult`, `ImageMetadata` |
| `schema/state.py` | `GlobalState`, struktur state graf |
| `schema/row_domains.yaml` | Domain berdasarkan label, bukan prediksi LLM |
| `schema/row_aliases.yaml` | Alias opsional untuk representasi retrieval; bukan file tidak terpakai |
| `agents/schema_matching/source_parsing.py` | Dua parser dan `ParsedAttribute`, menjaga posisi nilai terhadap varietas |
| `ingestion/workbook_profiler.py` | Profil struktur fisik workbook secara deterministik dan standalone |
| `agents/schema_matching/anchor.py` | Deteksi kolom identitas varietas |
| `agents/schema_matching/indexing.py` | Model embedding, persistent client, koleksi, reindex |
| `agents/schema_matching/retrieval.py` | Profil atribut, deteksi tipe heuristik, top-k kandidat |
| `agents/schema_matching/reranking.py` | Prompt pemilihan kandidat/NULL, pemanggilan provider terstruktur |
| `agents/schema_matching/normalize.py` | Pembersihan notasi dan pencocokan vocabulary konservatif |
| `agents/schema_matching/review_queue.py` | Event log enqueue/approve/revise serta patch error trace |
| `agents/drive_crawler.py` | Autentikasi service account, normalisasi folder ID, pagination dan filter MIME |
| `agents/vision_classification.py` | Deskripsi varietas, petunjuk filename, download citra, klasifikasi/consensus |
| `agents/tabular_update.py` | Penulisan URL citra tanpa menambah kolom varietas |
| `llm/providers.py`, `llm/vision_providers.py` | Klien provider melalui instructor dan penanganan fallback |
| `reliability/retry.py`, `rate_limit.py` | Backoff dan pembatas permintaan opsional |
| `reliability/verifier.py`, `wrappers.py` | Validasi ulang, pemanggilan aman, pencatatan error |
| `orchestrator/graph.py` | Graf stub, routing, penyimpanan dan resume checkpoint |
| `ui/app.py` | Upload, parameter pengguna, file sementara, pemanggilan pipeline |
| `ui/pipeline_runner.py` | Integrasi agen nyata yang dipakai UI |
| `ui/output_builder.py` | Pengelompokan nilai, konstruksi workbook, tabel preview |
| `ui/state.py` | Akses session state untuk hasil, log, input terakhir, status berjalan |
| `ui/pages/2_Progress.py` | Status agen, error trace, log run |
| `ui/pages/3_Hasil.py` | Inspeksi hasil/reasoning, debugger stub, download Excel |

## 5. Input dan skema kanonik

### Template

`data/canonical/template_kanonik.xlsx` menggunakan `Sheet1`, dengan header pada baris pertama: `Nomor`, `Karakter`, lalu kolom varietas referensi. Berdasarkan snapshot profiling, template memiliki 60 karakter, enam domain, dan sepuluh varietas referensi. Angka ini bukan konstanta yang boleh di-hardcode.

- Loader mengambil baris dengan `Nomor` dan label karakter tidak kosong.
- `CanonicalRow.id` (`r_1 ... r_N`) mengikuti posisi pemuatan dan dapat berubah jika template diurutkan ulang.
- `CanonicalRow.canonical_key` berasal dari `src/schema/row_keys.yaml`; ini adalah identitas semantik stabil yang tidak bergantung pada posisi baris. `CanonicalRow.label` tetap menjadi teks tampilan dan pencocokan yang dapat dibaca manusia.
- `schema_version` (`cabai-kms-canonical-v1`) menyatakan versi spesifikasi identitas kanonik, sedangkan `template_hash` adalah fingerprint tepat dari urutan/label template yang sedang dimuat. Reordering mengubah hash dan `r_N`, tetapi tidak mengubah canonical key.
- Domain dan alias dihubungkan melalui teks label yang di-trim. Nama sumber yang sama persis dengan label/alias terkurasi dipetakan secara deterministik tanpa bergantung pada recall embedding atau keputusan LLM; contohnya `Seeds per mature fruit` → `jumlah biji/buah masak`.
- Domain saat ini: `vegetatif`, `daun`, `bunga`, `buah`, `biji`, `lokasi`.
- Label `Lokasi` menampung informasi lokasi; `Gambar Daun/Batang/Buah/Bunga` untuk URL citra. Domain `Gambar Batang` adalah `vegetatif`.
- Varietas referensi digunakan untuk contoh nilai dan pengetahuan vision, bukan otomatis menjadi kolom output.
- Loader, output builder, dan penulis sel belum sepenuhnya bebas asumsi tata letak: pertahankan `Sheet1`, kolom A/B, dan baris karakter berurutan tanpa celah untuk output yang konsisten.

### Format row-oriented

Contoh: `data/samples/data_input.xlsx` dan `data_input_sintetis_1.xlsx`.

- Header satu baris: baris 1 berisi nama kolom (`Variety`, `Growth habit`, dan sebagainya); data mulai baris 2. Observasi pertama tetap disertakan.
- Header dua baris: baris 1 berisi kelompok/atribut mandiri, baris 2 berisi subheader. Bila subheader kosong, parser memakai header mandiri dari baris 1; data mulai baris 3.
- Mode otomatis mengenali header bertingkat melalui merged cells pada dua baris pertama. Header lengkap tanpa merge dianggap satu baris. Pilih **Jumlah baris header → 2 baris** untuk struktur bertingkat tanpa merge; pilihan 1/2 baris juga tersedia sebagai override.
- Header kosong, nama atribut duplikat dalam kelompok yang sama, atau struktur sparse yang ambigu ditolak dengan pesan pemeriksaan input. Subheader yang sama pada kelompok berbeda diperbolehkan dan ditampilkan sebagai nama berkualifikasi, misalnya `Young Fruit / Fruit Length` dan `Mature Fruit / Fruit Length`; nama leaf dan parent tetap dikirim terpisah ke retrieval/LLM. Deteksi otomatis belum merupakan parser universal untuk seluruh variasi workbook.
- Kolom identitas varietas dapat berpindah posisi; anchor detector memilihnya dari nama header. Referensi embedding mencakup `Variety` dalam bahasa Inggris. Jika kolom varietas tidak ditemukan, tidak memiliki nilai, atau observasi berisi data tetapi varietasnya kosong, runner berhenti sebelum indexing/LLM agar data tidak hilang diam-diam.
- Data beberapa observasi dengan nama varietas sama digabung; bukan dihitung rata-ratanya.

Contoh nyata `data_input.xlsx` berisi lokasi, koordinat, fisiologi, tanah, dan mikroklimat. Banyak atribut tersebut tidak memiliki padanan karakter morfologi di template; hasil `NULL` tidak otomatis berarti bug. Sampel sintetis merupakan bahan pengujian, bukan bukti akurasi pada data lapangan.

### Format transposed

Contoh: `data/samples/sample_transposed_sintetis.xlsx`.

- Parser mencari baris yang sel pertamanya sama persis dengan `Karakter` setelah trim.
- Sel berikutnya adalah nama varietas; atribut dan nilainya berada pada baris-baris setelah header.
- Boleh ada judul sebelum header. Jangan sisipkan kolom varietas kosong di tengah header karena parser memadatkan nama tetapi mengambil nilai berdasarkan posisi.
- Template kanonik dengan `Nomor` di kolom pertama **tidak langsung cocok** sebagai input parser transposed ini.

Format dipilih pengguna; aplikasi tidak otomatis menentukan orientasi. Semua parser saat ini memakai `openpyxl`, bukan parser CSV. Formula dibaca sebagai nilai tersimpan (`data_only=True`), sehingga workbook perlu sudah memiliki hasil kalkulasi dari aplikasi spreadsheet.

### Deterministic Workbook Structure Profiler

`src/ingestion/workbook_profiler.py` menyediakan `profile_workbook()` dengan kontrak Pydantic berversi `workbook-structure-v1`. Profiler membuka workbook dengan ekspresi formula dipertahankan dan mencatat seluruh worksheet secara berurutan: batas dimensi openpyxl versus batas konten nyata, koordinat/nilai/tipe/style sel non-kosong, merge, baris dan kolom tersembunyi, freeze panes, statistik baris/kolom, rentang kosong, serta candidate content regions.

Profiler ini standalone dan belum dipakai oleh `pipeline_runner` atau parser yang ada. Ia tidak menentukan orientasi, header, metadata, kolom varietas, atau tabel sebenarnya. `candidate_region` hanya persegi panjang konten yang dipisahkan gap baris/kolom kosong secara deterministik; kandidat tersebut bukan konfirmasi bahwa suatu area adalah tabel.

Penemuan sel dilakukan secara sparse terhadap sel openpyxl yang benar-benar terinstansiasi. Akses private `_cells` sengaja diisolasi dalam satu helper karena API publik `iter_rows` akan memindai persegi panjang penuh dan tidak aman untuk dimensi yang membengkak akibat formatting; perubahan ini tidak menambahkan interpretasi semantik.

### Normalisasi

`normalize()` merapikan token kosong, desimal koma, penulisan rentang menjadi `--`, pemisah multi-nilai menjadi `; `, dan spasi. Vocabulary matching memakai kecocokan tepat tanpa membedakan kapitalisasi terhadap contoh pada baris kanonik.

Tidak ada konversi satuan otomatis, penghitungan rerata, penerjemahan warna bebas ke kode RHS, atau penyusunan koordinat `Lokasi` secara terstruktur. Nilai ambigu dapat dipertahankan dengan catatan; runner UI saat ini mengambil `.value` tanpa meneruskan semua catatan normalisasi ke `error_trace`.

## 6. Kontrak data dan hasil

| Struktur | Field penting dan arti |
|---|---|
| `ParsedAttribute` | `attribute_name`, `structural_context`, `row_values`; `sample_values` menyaring nilai `None` |
| `SchemaMapping` | Atribut/konteks/format sumber, `target_canonical_row`, confidence `[0,1]`, reasoning, `normalization_required` |
| `SchemaMapping.target_domain` | Field turunan dari target row; `None` jika target `NULL` |
| `ImageMetadata` | `file_id`, `filename`, `mime_type`, `size`, `created_time`; tidak ada path hierarki |
| `VisionResult` | `classification_status` (`KNOWN/OTHER/UNCERTAIN`), `matched_variety`, `identified_part` (`DAUN/BATANG/BUAH/BUNGA`), confidence, bukti visual |
| `CellProvenanceRecord` | Run dan fingerprint sumber, atribut/konteks, varietas, sel nilai/header sumber bila tersedia, referensi kanonik posisi+stabil, nilai mentah+normal, keputusan acceptance, serta versi/hash skema untuk satu penulisan sel nyata |
| `PipelineRunResult` | Data/output lama ditambah `source_backend`, `source_ir_version`, dan laporan opsional `structure_shadow`; Source IR lengkap tidak dimasukkan |

`SchemaMapping` memvalidasi row ID terhadap skema default yang di-cache. Setelah mengubah template dalam proses Python yang sama, panggil `clear_default_schema_cache()` atau restart aplikasi.

Workbook keluaran mempertahankan struktur template, mengisi varietas dari sumber, serta membiarkan sel tak terpetakan kosong. Beberapa nilai pada sel yang sama ditambahkan dengan `; `, bukan menimpa nilai lama. Foto disimpan sebagai URL `https://drive.google.com/file/d/<file_id>/view`, **bukan gambar tertanam**, dan aksesnya tetap tunduk pada izin Drive. Sheet tambahan template dapat tetap ikut tersalin.

Preview dibentuk dari worksheet yang sudah mengalami penulisan tabular dan vision. Unduhan memakai bytes workbook tersebut. Hasil UI disimpan dalam session state; tidak otomatis disimpan sebagai file hasil permanen pada server.

`provenance_records` saat ini hanya mencakup penulisan kanonik dari schema matching; penulisan vision belum memiliki provenance pada fase ini. Provenance sel dibuat hanya setelah penulisan kanonik non-kosong benar-benar mengubah builder. `REVIEW`, `NO_WRITE`, nilai kosong, dan penulisan duplikat/no-op tidak menghasilkan provenance. Parser pipeline lama belum menyediakan koordinat sumber sehingga `source_cells` pada jalur produksi masih kosong. Source IR standalone sudah membedakan posisi logis dan koordinat fisik, tetapi belum dipropagasikan ke provenance kanonik.

## 7. Instalasi dan konfigurasi

### Dependensi

Proyek memakai Python dengan `pandas`, `openpyxl`, Pydantic, dotenv, YAML, LangGraph/SQLite checkpoint, ChromaDB, sentence-transformers, instructor, Groq/OpenAI-compatible clients, Google API/auth, tenacity, aiolimiter, Streamlit, dan pytest.

`requirements.txt` belum mengunci versi dan `pyproject.toml` belum mendeklarasikan rentang Python yang diuji. Jangan menganggap instalasi pada semua versi Python otomatis kompatibel. `torchvision` dicantumkan sebagai kebutuhan kompatibilitas stack embedding yang pernah digunakan. Versi pasangan yang tertulis pada komentar lama adalah catatan lingkungan terdahulu, bukan hasil verifikasi ulang audit ini. `google-genai` tidak dipakai langsung; Gemini memakai klien OpenAI-compatible. `langchain-core` dapat terpasang transitif lewat LangGraph, tetapi tidak diimpor langsung oleh kode proyek.

### PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
.\.venv\Scripts\python.exe -m streamlit run src/ui/app.py
```

Jika environment sudah tersedia, gunakan terlebih dahulu; jangan membuat ulang atau menghapusnya tanpa kebutuhan. Pemanggilan interpreter eksplisit tidak memerlukan aktivasi `Activate.ps1`. Untuk shell POSIX, interpreter environment umumnya `.venv/bin/python`, bukan `.venv/Scripts/python.exe`.

### Variabel lingkungan yang benar-benar dibaca kode

| Variabel | Kegunaan | Default/perilaku |
|---|---|---|
| `GROQ_API_KEY` | Provider teks utama | Jika kosong/gagal, mencoba Ollama |
| `OLLAMA_BASE_URL` | Endpoint fallback teks dan vision | `http://localhost:11434/v1` |
| `GOOGLE_API_KEY` | Gemini vision | Dibutuhkan ketika klasifikasi foto dipanggil |
| `GEMINI_MODEL_NAME` | Nama model vision Gemini | `gemini-flash-latest`, dibaca saat import |
| `OPENROUTER_API_KEY` | Voter kedua consensus | Opsional; bukan fallback langsung Gemini |
| `GOOGLE_DRIVE_CREDENTIALS_PATH` | JSON service account Drive | Wajib untuk akses Drive; bukan OAuth client JSON |
| `GOOGLE_DRIVE_FOLDER_ID` | Folder default bagi `list_images()` | Boleh ID/URL; UI tetap perlu input folder secara eksplisit |

`CHROMA_PERSIST_DIR` dari contoh konfigurasi lama **tidak dibaca kode** dan telah dihapus dari `.env.example`. Default sebenarnya adalah `data/.chroma/`, ditentukan di `indexing.py`. API indexing/retrieval menerima parameter lokasi penyimpanan; UI tidak menyediakan pengaturan lokasi tersebut.

Nama model lain berupa konstanta kode: teks Groq `llama-3.3-70b-versatile`, teks Ollama `llama3.1:8b`, voter kedua OpenRouter `qwen/qwen2.5-vl-72b-instruct`, fallback vision Ollama `qwen2.5-vl:7b`. Embedding menggunakan `paraphrase-multilingual-MiniLM-L12-v2`.

`.env` dimuat ketika modul provider/crawler diimpor. Restart aplikasi setelah mengganti konfigurasi. Lihat [DRIVE_SETUP.md](DRIVE_SETUP.md) untuk pengaturan akun dan akses folder.

## 8. Penggunaan UI dan API Python

### Alur pengguna

1. Jalankan Streamlit, lalu buka alamat lokal yang ditampilkan terminal.
2. Unggah `.xlsx` dan pilih orientasi yang sesuai.
3. Kosongkan folder Drive untuk uji tabular, atau isi URL/ID folder berisi foto yang dapat diakses service account.
4. Klik **Jalankan Pipeline**; log diperbarui pada halaman Input selama proses sinkron berjalan.
5. Buka **Progres** untuk status dan log run. Halaman ini bukan monitor worker latar belakang.
6. Buka **Hasil** untuk tabel kanonik, mapping/confidence/reasoning, dan klasifikasi citra.
7. Periksa warning dan sel hasil, kemudian unduh Excel.

Input upload disalin ke file sementara dan dihapus dalam blok `finally`. Tidak ada antrean job atau kemampuan resume proses UI. Saat run baru dimulai, hasil sebelumnya dibersihkan dari session state agar run gagal tidak menawarkan unduhan lama.

### Memanggil runner dari Python

Contoh berikut melakukan pemrosesan nyata dan dapat memanggil provider teks:

```python
from pathlib import Path
from src.ui.pipeline_runner import run_pipeline_ui

result = run_pipeline_ui(
    Path("data/samples/sample_transposed_sintetis.xlsx"),
    source_format="transposed",
    drive_folder_id=None,
    k=8,
    max_images=5,
    on_progress=print,
)
print(result.canonical_df)
print(result.error_trace)
# result.workbook_bytes adalah konten .xlsx untuk disimpan/diunduh.
```

`sheet_name` dan `header_rows=None/1/2` dapat disuplai melalui API Python (`None` berarti otomatis; header_rows hanya untuk row-oriented). Consensus dapat digunakan melalui `VisionSession(consensus=True)` atau parameter klasifikasi, tetapi `run_pipeline_ui()` belum mengekspos mode tersebut.

## 9. Review dan evaluasi

### Manual review queue

Mapping masuk queue jika target `NULL` atau confidence `< 0.6`. File default: `data/review/manual_review_queue.jsonl`. Setiap enqueue/approve/revise menambahkan event baru; status terkini ditentukan oleh event terakhir untuk `item_id` yang sama.

Inspeksi tanpa mengubah data:

```python
from src.agents.schema_matching.review_queue import list_pending

for item in list_pending():
    print(item.item_id, item.mapping.source_attribute, item.reason)
```

API `approve(item_id, resolved_by=...)` menandai persetujuan, sedangkan `revise(item_id, corrected_mapping, resolved_by=...)` menyimpan koreksi berupa `SchemaMapping`. Keduanya mengubah queue, **bukan workbook yang sudah dibuat**. Belum ada replay hasil koreksi ke pipeline, dan UI belum menyediakan tombol untuk keduanya.

Kegagalan provider tanpa mapping serta masalah vision dicatat melalui trace tertentu, bukan semuanya menjadi `ReviewItem`. Jangan menyamakan jumlah queue, jumlah error trace, dan jumlah kesalahan di output.

### Harness evaluasi

Gunakan nama output baru agar label manual historis tidak tertimpa:

```powershell
.\.venv\Scripts\python.exe eval/review_schema_matching.py --help
.\.venv\Scripts\python.exe eval/review_schema_matching.py --file data/samples/data_input.xlsx --format row-oriented --output data/outputs/review_row_run01.xlsx
.\.venv\Scripts\python.exe eval/review_schema_matching.py --file data/samples/sample_transposed_sintetis.xlsx --format transposed --output data/outputs/review_transposed_run01.xlsx
```

Ganti nama output jika file tersebut sudah ada. Argumen tersedia: `--file`, `--format`, `--sheet`, `--output`, `--k`. Default top-k adalah 8; retrieval membatasi k pada 5–10.

Kolom laporan: `source_attribute`, `source_format`, `predicted_row`, `predicted_label`, `target_domain`, `confidence`, `normalization_required`, `reasoning`, serta kolom kosong `gold_row`, `is_correct`, `catatan`. Urutan confidence rendah lebih dahulu.

**Peringatan:** menjalankan harness tanpa `--output` menulis ke `data/gold/schema_matching_review.xlsx` dan dapat menimpa anotasi. Dua workbook di `data/gold/` dipertahankan; belum diverifikasi ulang kelengkapan anotasinya. Tidak ada klaim precision/recall/F1 atau akurasi vision berdasarkan keberadaan file itu saja.

## 10. Reliability dan checkpoint

- Retry menggunakan tenacity, default tiga percobaan, backoff dasar 1 detik dan maksimum 10 detik.
- Verifier mengizinkan dua revisi setelah percobaan pertama. Pada implementasi sekarang revisi memanggil closure lagi; bukan critic LLM terpisah yang menyusun umpan balik baru.
- Provider/instructor memiliki mekanisme retry internal. Lapisan-lapisan tersebut dapat memperbesar total request dan waktu tunggu; tiga percobaan wrapper bukan batas total request eksternal.
- `safe_rerank()` menangani mapping gagal/NULL/low-confidence. `safe_classify_image()` mencoba download, klasifikasi, dan mencatat kegagalan/`UNCERTAIN`.
- `RateLimiter` tersedia melalui parameter `rate_limiter`, tetapi nilai default adalah `None` dan UI tidak mengaktifkannya.
- Gemini utama tidak memiliki fallback sendiri. OpenRouter → Ollama hanya jalur voter kedua pada consensus.

Graf stub berurutan `schema_matching -> drive_crawler -> vision_classification -> tabular_update -> finalization`, dengan routing vision retry/manual_review/continue. `run_pipeline()` dan `resume_pipeline()` memakai `thread_id` dan file SQLite yang sama. Default file adalah `data/.checkpoints/orchestrator.sqlite`.

Checkpoint menyimpan state graf stub, bukan nilai intermediate dari agen nyata di UI. Kegagalan checkpoint di akhir runner masih dapat membuat UI melaporkan run gagal walaupun workbook sudah dibangun di memori. Jangan menghapus database ketika aplikasi sedang berjalan atau ketika riwayat debugger masih diperlukan.

## 11. Pengujian dan troubleshooting

### Perintah tes

Tes lokal tanpa kelompok embedding/live fallback:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider -m "not indexing and not llm_fallback_live"
```

Tes embedding/retrieval/anchor (model harus sudah di-cache atau dapat diunduh):

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m indexing
```

Seluruh suite, termasuk percobaan koneksi localhost untuk fallback:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Marker `llm_fallback_live` menguji koneksi fallback nyata yang diharapkan gagal saat server Ollama tidak berjalan. Baca tes sebelum menjalankannya pada mesin dengan Ollama aktif. Sebagian besar tes agen memakai klien mock/injeksi; `test_ui.py` memakai `Streamlit AppTest`, bukan browser end-to-end dengan API produksi.

Kelompok tes mencakup skema/kontrak, indexing/retrieval/anchor, reranking/normalisasi/review, Drive/vision/provider, penulisan output, retry/limiter/verifier/wrappers, graf/resume, dan halaman UI. `test_source_parsing.py` menguji header satu/dua baris serta sampel lama. `test_pipeline_runner.py` memeriksa alur parsing sampai bytes Excel dan kesamaan preview dengan workbook yang dibaca ulang, dengan provider/index/checkpoint mock; ini belum membuktikan akurasi model atau integrasi seluruh layanan nyata.

Hasil verifikasi audit terkini dicatat di [CHECKPOINTS.md](CHECKPOINTS.md), terpisah dari pengujian layanan eksternal terdahulu.

### Gejala umum

| Gejala | Pemeriksaan/tindakan |
|---|---|
| `.venv` gagal menjalankan Python | Periksa instalasi Python asal dan izin eksekusi; environment virtual tidak portabel antarinstalasi/mesin |
| `ModuleNotFoundError` | Pastikan pip dan Streamlit/pytest menggunakan interpreter `.venv` yang sama |
| Upload CSV gagal | Simpan sebagai `.xlsx` dengan struktur §5; mengganti ekstensi saja tidak cukup |
| Header `Karakter` tidak ditemukan | Untuk transposed, tempatkan teks tersebut di kolom pertama header |
| Kolom varietas tidak ditemukan | Periksa log header, pilihan 1/2 baris, serta nama kolom identitas; runner menghentikan run sebelum pemetaan |
| Banyak `NULL` | Cocokkan cakupan atribut sumber dengan template; atribut mikroklimat belum tentu punya target |
| Banyak sel kosong | Bisa karena tidak ada padanan, provider gagal, nilai kosong, atau identitas varietas hilang; lihat log dan mapping |
| Foto tidak ditulis | Periksa `KNOWN`, kecocokan nama varietas output, label baris Gambar, dan log alasan penolakan |
| Folder `.env` terisi tetapi vision dilewati | UI tidak memakai folder env sebagai fallback; isi URL/ID pada form |
| Kredensial/Drive 404 | Periksa path JSON service account, ID folder, dan sharing Viewer; jangan tempel isi private key pada log |
| Groq/Gemini quota/auth/model error | Periksa akses akun, kuota dan konfigurasi; audit ini tidak memverifikasi ketersediaan model secara live |
| Embedding lambat/gagal di awal | Periksa cache model, akses unduhan, dan kompatibilitas dependensi embedding |
| Mengubah alias/domain tidak mengubah retrieval | Restart aplikasi; fingerprint representasi akan memicu rebuild indeks. Gunakan `ensure_indexed(force=True)` jika indeks berasal dari versi lama |
| Hasil lama dari sebelum pembaruan | Restart aplikasi dan jalankan ulang pipeline; versi baru membersihkan hasil lama ketika run baru dimulai |

## 12. Keterbatasan dan pekerjaan lanjutan

Temuan berikut adalah batas implementasi, **bukan fitur yang diperbaiki dalam audit dokumentasi ini**:

1. **Review sudah memblokir penulisan, tetapi koreksi belum interaktif.** Gerbang Phase 1 memastikan hanya `AUTO_ACCEPT` yang menulis; `REVIEW` dan `NO_WRITE` tidak mengubah workbook kanonik. Queue review belum tersambung ke editor UI dan replay hasil koreksi.
2. **CSV dan parsing umum belum tersedia pada UI.** Uploader menawarkan CSV, tetapi pipeline masih memakai parser lama dengan tata letak tertentu. Phase 4 dapat merepresentasikan judul sebelum tabel, header bertingkat, merge, dan layout transposed secara standalone setelah verifikasi, tetapi belum diintegrasikan. T03 dan T04 sudah diverifikasi; enam dummy lainnya belum diverifikasi pada perbaikan ini.
3. **Validasi anchor kini menghentikan runner.** Header salah/ambigu atau identitas varietas yang hilang menghasilkan error sebelum pemetaan. Error provider dan mapping NULL masih harus diperiksa terpisah; validasi input bukan jaminan semua atribut akan terpetakan.
4. **Koreksi manual belum diterapkan ulang.** Queue belum tersambung ke editor UI, replay workbook, atau identitas run yang lengkap.
5. **Graf masih stub.** Checkpoint/resume tidak memulihkan proses agen nyata; routing stub tidak menjadi jaminan reliability alur UI.
6. **Rate limiter belum dipasang pada runner.** Retry provider juga dapat mengulangi error konfigurasi/kuota yang tidak akan pulih hanya dengan retry.
7. **Trace belum mencakup semua jalur.** Catatan normalisasi dan alasan sel vision tidak ditulis hanya sebagian tampil di log; label validasi UI tidak mewakili semua masalah data.
8. **Vision berlandaskan varietas template.** Nama input bisa berbeda dari referensi; belum ada crosswalk spesies/varietas, dan tidak ada numeric confidence gate tambahan pada penulisan foto `KNOWN`.
9. **Lokasi belum disusun sesuai rancangan komposit.** Pemetaan beberapa atribut ke `Lokasi` baru menggabungkan nilai, belum merakit nama/koordinat/elevasi dengan semantik khusus.
10. **Deteksi perubahan model embedding masih manual.** Fingerprint indeks sudah mencakup representasi baris, termasuk contoh nilai, alias, dan domain, sehingga perubahan data tersebut memicu rebuild otomatis. Namun, penggantian nama/versi model embedding masih perlu diikuti force reindex atau direktori indeks baru.
11. **Belum ada evaluasi kuantitatif lengkap.** Macro-F1 per domain, gold vision, dataset holdout, dan analisis error perlu dibangun; sampel sintetis tidak menggantikan validasi lapangan.
12. **Belum siap produksi.** Belum tersedia lockfile dependensi, autentikasi aplikasi, job queue, isolation per pengguna untuk review/checkpoint, kebijakan retensi, deployment teruji, dan monitoring layanan.

Prioritas lanjutan yang masuk akal: validasi input dan pemblokiran mapping bermasalah; review/replay dan trace; integrasi graf dengan agen nyata serta limiter; terakhir reproduksibilitas dan evaluasi terukur. Perubahan semantik penelitian tetap perlu keputusan pemilik proyek.

## 13. Pemeliharaan, keamanan, dan pembersihan

### Mengubah template

1. Simpan salinan aman template sebelum mengedit.
2. Pertahankan tata letak yang didukung, label unik, serta `Nomor`/`Karakter` pada sheet utama.
3. Tambahkan atau sesuaikan label pada `row_domains.yaml` dan alias bila diperlukan.
4. Restart aplikasi agar cache kontrak/deskripsi varietas diperbarui.
5. Jalankan `ensure_indexed(force=True)` setelah perubahan contoh, domain, alias, atau model; ini mengganti indeks turunan, bukan template.
6. Jalankan tes skema, indexing, dan output. Tinjau ulang gold/queue lama karena row ID dapat berubah saat urutan berubah.

### Data dan rahasia

- Jangan commit `.env`, JSON private key, isi upload sensitif, atau token provider.
- Share folder Drive minimum Viewer kepada service account; program tidak membuat folder publik.
- Provider teks menerima nama/konteks/contoh nilai; provider vision menerima bytes foto, filename, dan deskripsi template. Pastikan data memang boleh dikirim ke layanan tersebut.
- Queue dan checkpoint dapat memuat input/path/reasoning. Jangan membagikannya sebagai log publik tanpa pemeriksaan.
- `data/gold/` dapat mengandung anotasi manusia; jangan jalankan harness dengan output menimpa file tersebut secara tidak sengaja.
- Output baru dapat ditempatkan di `data/outputs/` (diabaikan Git); folder ini dibuat ketika diperlukan oleh harness.

### Kebijakan pembersihan audit

| Target | Keputusan dan alasan |
|---|---|
| `.pytest_cache/` | Hapus cache tes yang dapat dibuat ulang |
| `__pycache__/` di `src/`, `tests/`, `eval/` | Hapus bytecode turunan, bukan source |
| `eval/metrics/` kosong | Hapus placeholder tanpa implementasi; Macro-F1 tetap dicatat sebagai rencana |
| `.venv/` | Pertahankan agar instalasi dependensi tidak hilang |
| `data/.chroma/` | Pertahankan karena dipakai retrieval; bukan folder tidak terpakai |
| `data/.checkpoints/orchestrator.sqlite` | Pertahankan riwayat debugger; file ini sudah tracked sebelum audit |
| `data/review/`, `data/gold/` | Pertahankan antrean/hasil review; bisa memuat kerja manusia |
| Template, tiga sampel, YAML, `__init__.py` | Pertahankan input, fixture, konfigurasi, dan struktur paket |
| Dokumentasi historis | Pertahankan keputusan/evidence; beri keterangan historis bila kondisi sudah berubah |
| `.env`, `credentials.json` | Tidak dibaca isinya atau dihapus dalam audit ini |

Cache yang dihapus tidak memerlukan pemulihan: Python/pytest akan membuatnya lagi. Folder metrics kosong dapat dibuat kembali ketika implementasi evaluasi ditambahkan. `.gitignore` mengabaikan checkpoint baru dan output lokal; pola ignore **tidak** menghentikan tracking database checkpoint yang sudah masuk Git. Melepas database itu dari tracking memerlukan perubahan indeks Git tersendiri dan tidak dilakukan pada audit ini.

Lihat [CHECKPOINTS.md](CHECKPOINTS.md) untuk hasil pembersihan dan verifikasi aktual; lihat [DESIGN_DECISIONS.md](DESIGN_DECISIONS.md), [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md), dan [PROFILING.md](PROFILING.md) untuk konteks penelitian.
