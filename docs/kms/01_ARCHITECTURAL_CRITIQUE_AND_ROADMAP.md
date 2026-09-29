# 01. Architectural critique and evolution roadmap

## 1. Verdict

Masalah utama bukan model yang kurang besar, melainkan **belum adanya kontrak pengetahuan yang tahan terhadap waktu, koreksi, kegagalan proses, dan pengulangan**. Pipeline dapat menghasilkan spreadsheet benar hari ini, tetapi tanpa arsip sumber, identitas observasi, keputusan reviewer dan versi konfigurasi, hasil itu sulit direproduksi atau dipertanggungjawabkan enam bulan kemudian.

Urutan investasi yang disarankan: evidence persistence -> review transaction -> private assets -> reproducibility/evaluation -> worker decoupling -> learned retrieval -> portal kolaboratif. Mengganti UI terlebih dahulu hanya memindahkan masalah persistensi ke antarmuka baru.

## 2. Temuan audit berbasis file

Rujukan file dan dokumentasi primer terdaftar dalam `SOURCES.md`. Audit ini tidak mengklaim telah menjalankan seluruh repository atau menyamakan branch publik dengan checkout VPS.

| Temuan | Bukti sumber | Implikasi | Respons enhancement |
|---|---|---|---|
| Review bukan sepenuhnya in-memory | `3_Hasil.py`, `review_queue.py`, `review_replay.py` memakai JSONL append-only dan replay | Ada fondasi yang baik, tetapi belum menjadi transaksi pusat lintas sesi/proses | Pertahankan replay; simpan full review snapshot pada revisi draft PostgreSQL sebelum mengakui perubahan lokal |
| Provenance per sel sudah ada | `src/schema/provenance.py`, `pipeline_runner.py` | Jangan membuat ulang lineage dari tampilan Excel saja | Adapter mengambil provenance asli dan menolak sel berisi tanpa bukti accepted |
| `canonical_key` sudah stabil; `r_N` positional | `src/schema/canonical.py` | Row number tidak boleh menjadi identitas FK | Semua referensi KMS memakai canonical_key/UUID |
| `template_hash` hanya urutan posisi/label | `_read_template_labels` | Alias, examples, units, prompt, model dapat berubah tanpa hash ini berubah | Simpan catalog snapshot/hash dan config fingerprint tambahan; release manifest perlu memasukkan seluruh dependensi perilaku |
| Domain repo lebih luas daripada organ | `row_domains.yaml`: vegetatif dan lokasi | Memaksa semua karakter menjadi daun/buah merusak semantik | Simpan source_domain; lokasi memiliki organ_domain NULL; batang/habitus dipetakan eksplisit |
| File upload sementara dihapus setelah proses | `src/ui/app.py` | Hash tidak berguna untuk replay jika bytes asli tidak disimpan | Arsip source bytes sebelum pipeline; hasil awal juga diarsipkan untuk replay review |
| Graph mengimpor fungsi dari UI runner | `src/orchestrator/graph.py` mengimpor `src.ui.pipeline_runner` | Dependency direction terbalik; UI sulit diganti | Fase berikutnya ekstrak acquisition application service; paket awal mengisolasi storage/API tanpa rewrite berisiko |
| Hasil vision semula tidak membawa identitas asset lengkap | `vision_classification` pada graph | Filename bukan identitas; redownload Drive dapat mengambil versi foto berbeda | Hook membawa Drive ID, original SHA, inference SHA, transform profile dan asset ID |
| Ada exact retrieval/Source IR yang sudah dikembangkan | `docs/PROJECT_GUIDE.md` | Tidak perlu mengusulkan fitur yang sudah ada seolah belum dibuat | Reuse backend pilihan repo; jangan paksa Chroma atau Source IR baru tanpa evaluasi |
| Dokumentasi provider tertinggal dari kode | README menyebut jalur lama, kode vision telah mengenal 9Router | Audit konfigurasi berdasarkan kode + runtime manifest, bukan README saja | Tidak mengganti model/gateway. Catat alias permintaan dan model/provider yang benar-benar melayani |

## 3. Data lifecycle: dari file menjadi evidence package

User membuat satu **batch akuisisi** berisi beberapa file, lokasi/kampanye penelitian, pemilik, dan konteks pengamatan. Preflight menghasilkan ringkasan struktur, sheet, daftar varietas, unit, potensi collision identitas, serta estimasi atribut yang perlu diperiksa. Sesudah sumber terarsip, sistem dapat mengakui penerimaan job; UI tidak harus menunggu model.

Review ideal bukan spreadsheet raksasa: tampilkan hanya keputusan berisiko, dikelompokkan berdasarkan pola header dan konteks sumber. Setiap kartu berisi potongan sel asli, target usulan, contoh nilai, perubahan sebelum/sesudah, unit, verifier, alasan abstain, dan dampak terhadap pengetahuan existing. Bulk approve diperbolehkan hanya untuk kelompok yang benar-benar identik konteks dan kebijakannya; sediakan sampling terstruktur untuk auto-accepted items.

Alur target:

```text
REGISTERED -> SOURCE_ARCHIVED -> PREFLIGHTED -> QUEUED -> RUNNING
 -> AWAITING_REVIEW -> READY_TO_COMMIT -> COMMITTED -> PUBLISHED
                         |                    |
                    AMENDMENT             OUTBOX EVENT
```

`FAILED_RETRYABLE`, `FAILED_TERMINAL`, `CANCEL_REQUESTED`, `CANCELLED` harus eksplisit dalam fase worker. Jangan menyamakan pembatalan browser dengan pembatalan job. Status `STAGED/COMMITTED` yang ada pada paket adalah **status publikasi KMS**, bukan seluruh status eksekusi job di atas.

Setelah commit, user memperoleh receipt dan permalink run. Download XLSX tetap tersedia sebagai proyeksi pertukaran data, bukan satu-satunya salinan pengetahuan. Koreksi sesudah publikasi menjadi amendment run, bukan update diam-diam pada histori.

## 4. Terobosan yang relevan secara ilmiah

### 4.1 Evidence-first, bukan variety-first saja

Varietas merupakan entitas, tetapi tinggi tanaman, panjang buah, warna, dan lokasi adalah **hasil observasi pada kondisi tertentu**. Grain ilmiah yang lebih tepat: varietas/accession + specimen/plot + tanggal + fase tumbuh + lokasi + metode + ulangan. Jangan menganggap nilai terakhir sebagai kebenaran biologis universal.

Paket menyediakan `value_observations` append-only dan `variety_character_values` sebagai current projection untuk kompatibilitas permintaan awal. Fase selanjutnya menambahkan `accessions`, `specimens`, `observation_events`, `measurement_methods` serta koordinat yang aksesnya dibatasi. Jangan menciptakan specimen ID atau waktu observasi palsu ketika sumber tidak memilikinya; gunakan unknown dan antrean kurasi. `acquisition_date` bukan pengganti tanggal pengamatan.

Nama lokal tidak selalu menentukan varietas unik. Upsert canonical_name aman hanya setelah identitas dalam satu katalog/workspace disepakati. NFKC/casefold mengatasi perbedaan pengetikan, bukan sinonim biologis atau homonim. Untuk dua sumber yang memakai nama sama bagi accession berbeda, hentikan merge dan minta keputusan curator; jangan menambah fuzzy merge otomatis.

### 4.2 Self-improving ingestion yang tidak meracuni dirinya sendiri

Setiap keputusan reviewer menyimpan input, konteks header, usulan awal, target final/NO_MATCH, raw values, identitas sumber, schema_version, template_hash, actor autentikasi, dan waktu. Semua keputusan final masuk `gold_examples` pada commit. Label NO_MATCH adalah contoh negatif penting, bukan dibuang.

Pisahkan tiga lapis:

1. **Evidence**: keputusan manusia yang pernah dibuat, termasuk yang kemudian diperdebatkan.
2. **Few-shot candidate**: contoh sesuai source_scope, versi schema dan konteks yang dapat dipertimbangkan untuk prompting. Konten tetap data tak tepercaya, bukan instruksi model.
3. **Exact alias**: aturan deterministik dengan cakupan sempit, dipromosikan curator setelah evaluasi dan pemeriksaan konflik. Tidak otomatis mendapat confidence=1 hanya karena seorang reviewer pernah menyetujui satu contoh.

`LearningRepository.promote/resolve/revoke` menyediakan penyimpanan, conflict check, scoped lookup, dan pencabutan. Alias tidak mengubah `row_aliases.yaml` global. Promosi merekam referensi evaluasi, tetapi kode tidak memverifikasi isi laporan evaluasi itu; curator tetap bertanggung jawab. Belum ada fine-tuning model, active learner trainer, atau retriever hook otomatis yang diam-diam mengubah baseline.

Saat akan diintegrasikan: lakukan shadow lookup sebelum semantic retrieval, bandingkan dengan baseline pada dataset tertahan, lalu lakukan rollout terbatas per source_scope. Gunakan versioned alias snapshot pada satu run agar promosi di tengah run tidak mengubah keputusan sebagian atribut.

### 4.3 Confidence bukan probabilitas benar

Pydantic memverifikasi bentuk keluaran, bukan kebenaran pemetaan. Exact name match juga bisa salah bila label ambigu lintas organ. Nilai model 0.6 bukan jaminan 60% akurasi; ukur selective precision versus coverage pada data held-out. Pisahkan confidence pemetaan, validitas normalisasi, kepastian entity resolution, dan kepastian vision.

Prioritaskan review dengan kombinasi retrieval ambiguity, margin antar-candidate, verifier issues, unit mismatch, perubahan terhadap nilai lama, dan dampak ilmiah. Aktifkan auto-accept per kelompok karakter hanya ketika metrik kelompok itu memenuhi ambang yang disepakati. Angka seperti precision >=99% dapat menjadi **target internal**, bukan hasil yang telah dibuktikan di repo ini.

### 4.4 Evaluasi yang menghindari leakage

Pisahkan train/gold dan test berdasarkan file, tim sumber, lokasi/kampanye atau waktu; jangan hanya acak baris yang nyaris sama. Gold dari file uji tidak boleh kembali menjadi few-shot untuk menilai file itu. Untuk vision, lakukan ablation dengan filename disamarkan karena kode memasukkan petunjuk nama file; ukur organ accuracy terpisah dari kecocokan varietas. Dua akun pada model sama bukan dua sumber penilaian independen.

Ukuran yang disarankan: recall@K untuk candidate retrieval, precision/coverage selective acceptance, exact normalized-value agreement, precision NO_MATCH, human override rate, disagreement per domain, latency p50/p95, token cost per accepted attribute, jumlah konflik commit, dan missing-provenance rate. Buat evaluation manifest dengan sumber, schema, aliases, prompt, normalizer, verifier, embedding weights dan actual provider/model version. Existing evaluation fingerprint disimpan, tidak dianggap otomatis mencakup semua itu.

## 5. Decoupling dan eksekusi async

Target dependency direction:

```text
Streamlit / Next.js -> FastAPI -> application services -> domain contracts
                                      |                      |
                           PostgreSQL repository        LangGraph engine
                                      |                      |
                               private object store    external model adapters
```

Jangan pindahkan fungsi yang sama ke FastAPI lalu menjalankan ingestion panjang di HTTP request dan menyebutnya background processing. `FastAPI.BackgroundTasks` bukan antrean durable. Pada fase async, API menyimpan job + outbox dispatch dalam satu transaksi, lalu mengembalikan HTTP 202/job ID. Worker mengambil job, memuat source dari URI privat, dan melaporkan node progress. UI polling sederhana cukup untuk awal; SSE dapat ditambah dengan sequence/event ID sehingga reconnect tidak kehilangan urutan.

Untuk satu VPS dan volume rendah, gunakan antrean PostgreSQL berbasis lease dan `FOR UPDATE SKIP LOCKED` yang teruji, atau Celery jika tim sudah mengoperasikan broker. Satu file menjadi satu job; satu batch memiliki daftar child jobs. Hindari satu transaksi raksasa untuk seluruh batch: atomic per run, lalu ringkas partial success batch. Batas concurrency ditentukan API provider dan kapasitas CPU/I/O, bukan semata 54.9 GB RAM yang dilaporkan.

Celery cocok untuk task terpisah dengan retry/backoff dan backpressure, tetapi `acks_late` bukan exactly-once. Temporal layak ketika ada workflow lintas layanan yang berlangsung berhari-hari, human approval, timer, compensation dan versioned replay. Keduanya tetap membutuhkan idempotent side effects. LangGraph tetap digunakan untuk logika agent/state; pilihan broker/durable workflow tidak otomatis menggantikannya.

Checkpointer PostgreSQL LangGraph adalah migrasi terpisah. Jangan menyimpan object besar seperti workbook bytes dan prepared Python bundles tanpa menilai serializer, pertumbuhan checkpoint, retention dan keamanan deserialisasi. Simpan referensi artifact dan state kecil; lakukan setup checkpointer dengan role tersendiri. KMS business tables tidak boleh disamakan dengan tabel checkpoint internal.

## 6. Stack comparison

| Komponen | Stack saat ini / alternatif repo | Rekomendasi | Keunggulan dan trade-off |
|---|---|---|---|
| KMS fakta & review | XLSX, session state, JSONL, SQLite checkpoint | PostgreSQL relasional + JSONB evidence | Transaksi, indeks, concurrency, histori; perlu operasi backup/migrasi |
| Vector retrieval | Chroma + multilingual MiniLM; ada backend exact opt-in | Pertahankan baseline; ukur pgvector exact lebih dulu | Satu lifecycle backup/filter/join; bukan berarti otomatis lebih akurat |
| Vector index | Top-K kecil | Exact cosine untuk katalog kecil; HNSW setelah benchmark | HNSW menukar recall/memori/build cost untuk latency; tidak diperlukan karena sekadar tren |
| Graph pengetahuan | Belum dibutuhkan | FK/recursive SQL dulu; Apache AGE hanya bila query graph terbukti dominan | AGE melengkapi relasional, bukan pengganti embedding index |
| State machine | LangGraph + SQLite | LangGraph; PostgresSaver setelah state diperkecil | Checkpoint lintas proses; butuh migrasi serializer, retention, role terpisah |
| Eksekusi job | UI sinkron | API + durable worker; PostgreSQL queue/Celery sesuai kebutuhan | UI tidak terblokir; retry, lease, rate limit dan cancel harus nyata |
| Workflow panjang | Belum diperlukan | Temporal bila koordinasi durable kompleks | Replay/timer/compensation; platform dan workflow versioning lebih berat |
| Backend API | Logic melalui UI runner | FastAPI + application service | Bisa mengubah client tanpa mengganti persistence; jangan membuat microservice per agent |
| Driver database | Belum ada business DB | SQLAlchemy 2 + psycopg 3 sinkron untuk tahap awal | Mudah diaudit dan terintegrasi; async berguna bila concurrency I/O terukur menuntutnya |
| Media | Drive URL/filename dalam hasil | CAS private R2/S3, local CAS transisi | Pisah failure domain, hash integrity; latency/network/credentials menjadi trade-off |
| UI | Streamlit 3 halaman | Streamlit + inspector dulu; React/Next setelah kebutuhan jelas | Murah untuk ilmuwan; portal kolaboratif perlu auth, form state dan UX lebih kaya |
| Frontend framework | Usulan Next.js 15 | Gunakan versi LTS yang masih didukung saat rollout | Pada verifikasi 29-09-2026: 16 Active LTS, 15 Maintenance; hindari pin versi hanya karena prompt awal |

## 7. Tahapan promosi, bukan jadwal yang dibuat-buat

**Fase A -- paket ini:** persistence, review recovery, private media, API, immutable observations, idempotent commit, outbox. Exit: integration SQL, regression repo, source/vision roundtrip dan restore drill lulus. `KMS_ENABLED` tetap false sebelum itu.

**Fase B -- scientific reproducibility:** acquisition manifest lengkap, entity resolution, taxonomy/unit registry curator-owned, specimen/observation grain, calibrated selective acceptance, gold evaluation report. Exit: metrik pada held-out source mencapai target yang disepakati.

**Fase C -- async operations:** durable jobs/batches, small-state Postgres checkpoints, polling/SSE, provider budgets, retry/cancel, worker crash recovery. Exit: crash/restart tidak kehilangan accepted jobs dan tidak membuat double publication.

**Fase D -- collaborative portal:** OIDC, scoped RBAC, tenant_id pada seluruh constraints/indexes/objects, RLS yang diuji lintas tenant, dataset releases, approvals, Next.js/React. Mulai ketika reviewer bersamaan, akses antar tim, permalink, dan bulk workflow memang diperlukan; bukan berdasarkan jumlah baris semata.

## 8. Explicit durability contract

API mengakui commit hanya setelah transaksi database selesai. Retry dengan identitas sama mengembalikan receipt yang sama. File publication terjadi sebelum DB reference. Notifikasi menggunakan at-least-once outbox; consumer wajib dedup event ID. Jangan memakai file hash sebagai satu-satunya run ID: file sama dapat diakuisisi ulang dengan schema/config berbeda.

`fsync` dan synchronous_commit melindungi jenis kegagalan lokal tertentu, bukan kebakaran host atau pencurian akun. Backup file database ke disk VM yang sama bukan disaster recovery. Terapkan off-host base backup + WAL archive, retention, alarm archive lag, restore test, dan bila diperlukan synchronous standby di failure domain berbeda. Tetapkan RPO/RTO numerik berdasarkan risiko dan uji, bukan klaim marketing zero loss.
