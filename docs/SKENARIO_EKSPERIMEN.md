# Protokol Eksperimen dan Evaluasi CABAI-KMS (versi 4, standar publikasi)

Disusun 31 Oktober 2026, diperbarui 1 November 2026. Dokumen ini adalah **protokol yang dibekukan sebelum eksperimen dijalankan** (pre-specified). Semua perubahan setelah pembekuan dicatat
sebagai deviasi pada bagian 12 (D1 sampai D9c). Metrik inti, ukuran F2, dan dua mode evaluasi: `docs/RENCANA_EVALUASI.md`. Data dan gold: `data_evaluasi/`. Hasil sementara: `docs/HASIL_SEMENTARA_EKSPERIMEN.md`.

**Status (1 November 2026):** eksperimen inti (atribut harness 3 pengulangan, atribut UI, foto kombinasi, foto Commons 160) **sudah dijalankan**; skor dihitung terhadap gold
yang diverifikasi penulis, belum gold dua anotator independen. Eksperimen F2 (skema kanonik dinamis, bagian 14) sedang dijalankan.

### Commit acuan per eksperimen

| Eksperimen | Commit | Catatan |
|---|---|---|
| Atribut, harness 3 pengulangan (R01, R02, N07, N09) dan N08 varian | `24e1037` + perbaikan kecil (harness) | pipeline pemetaan identik pada semua commit sesudahnya dengan saklar mati (uji regresi D7, D9a, D9b, D9c) |
| Atribut lewat UI (S01 sampai S03, N07, R01, N08 varian, S02, R02, N09) | `323f1e4` | S04 dan N08 asli ditolak sistem (kasus penolakan) |
| Foto kombinasi (S01 sampai S03), UI dan harness | `bc3c21b` | hasil pada `323f1e4` tidak dipakai (D6) |
| Foto Commons F1 sampai F8 (UI) | `bc3c21b` | 8 run, 20 foto per run |
| Uji fitur atribut baru E-A1 sampai E-A3 | `a16c5cc` | database terpisah |
| Eksperimen F2 (skema dinamis) | `060b29f` | saklar `KMS_DYNAMIC_SCHEMA` hidup, API dan database terpisah |

## Apa yang berubah dari versi 3 dan mengapa

| Standar paper | Kondisi versi 3 | Perubahan di versi 4 |
|---|---|---|
| Gold andal dengan kesepakatan antar-anotator | Gold dari satu anotator | Dua anotator manusia buta + adjudikasi + Cohen's kappa (bagian 4); template buta sudah disiapkan |
| Pemisahan data pengembangan dan data uji | Tidak ada | Partisi dev vs held-out dengan bukti kebocoran (bagian 3) |
| Baseline dan ablasi yang kuat | Hanya S1 (UI tidak punya mode lain) | Lapis harness terkontrol menghasilkan S1, S2, S4 dari satu run; S3 dan ablasi sebagai tambahan (bagian 2) |
| Variasi model diukur | Satu run per konfigurasi | Pengulangan 3 kali pada harness (bagian 5) |
| Uji signifikansi | Hanya CI | Paired bootstrap dengan koreksi Holm (bagian 6) |
| Ancaman validitas, reproduksi, etika | Sebagian | Bagian 9 sampai 11 |
| Skenario multimodal yang realistis | 1 kombinasi spreadsheet + Drive | 4 kombinasi spreadsheet + Drive 1 (bagian 8) |

---

## 1. Pertanyaan penelitian dan hipotesis (ditetapkan sebelum eksperimen)

| RQ | Pertanyaan | Hipotesis | Kriteria keputusan |
|---|---|---|---|
| RQ1 | Seberapa tepat pipeline memetakan label atribut spreadsheet ke 60 baris kanonik? | H1: Mapping F1 sistem penuh (S4) lebih tinggi daripada exact-name (S1) dan retrieval top-1 (S2) | Selisih F1 paired bootstrap, CI 95% tidak memuat 0, p dikoreksi Holm < 0,05 |
| RQ2 | Apakah atribut di luar kanonik dibiarkan tak terpetakan? | H2: recall atribut baru S4 lebih tinggi daripada S2 (retrieval top-1 yang selalu memetakan) | idem |
| RQ3 | Apakah fusi tiga sinyal menjaga klasifikasi foto saat nama file menyesatkan? | H3: macro-F1 V3 lebih tinggi daripada V2 pada kondisi MENYESATKAN, dan tidak lebih rendah daripada V1 pada kondisi lain | paired bootstrap per kondisi |
| RQ4 | Apakah varietas yang tidak ada di spreadsheet berstatus kandidat (OTHER), bukan ditautkan paksa? | H4: recall OTHER V3 melampaui V1 | paired bootstrap |
| RQ5 | Apakah sistem terdeploy (UI) memberi hasil setara dengan harness terkontrol? | H5: kesepakatan butir UI vs harness tinggi | proporsi butir identik dan selisih metrik; deskriptif |

| RQ6 | Apakah atribut di luar kanonik dapat diakuisisi menjadi baris kanonik tanpa merusak pemetaan ke baris template? (F2, bagian 14) | H6: Mapping F1 baris template pada mode adaptif tidak lebih rendah dari mode beku (selisih rata-rata di dalam variasi antar pengulangan) | selisih F1 template mode adaptif minus mode beku, dengan rentang antar pengulangan |
| RQ7 | Apakah atribut bermakna sama disatukan sehingga tidak ada baris duplikat, dan baris yang sudah diakuisisi dipakai ulang oleh dataset berikutnya? (F2) | H7: tingkat penggunaan ulang pada dataset berikutnya positif dan pasangan duplikat jarang | deskriptif: tingkat penggunaan ulang, baris dibanding kandidat, pasangan label sangat mirip |

Hipotesis dapat salah; hasil yang menolaknya dilaporkan apa adanya. RQ6 dan RQ7 bersifat eksploratori (tidak masuk koreksi Holm).

---

## 2. Desain tiga lapis

| Lapis | Tujuan | Cara menjalankan | Keluaran |
|---|---|---|---|
| **L1 Harness terkontrol** (utama, kuantitatif) | Skor utama, baseline, ablasi, pengulangan | Pipeline yang sama (commit dan model beku) dijalankan dari terminal VPS lewat `eval/create_mapping_annotations.py` (atribut) dan skrip foto yang memanggil `run_pipeline_ui`; keluaran memuat kolom retrieval lengkap | CSV per run, `evaluation_config_fingerprint` |
| **L2 Replikasi UI** (validasi sistem terdeploy) | Menunjukkan website yang dipakai pengguna memberi hasil setara; E2E nyata | 17 run lewat website (bagian 8), hasil diunduh dan disimpan | CSV unduhan per run |
| **L3 Studi kasus Indonesia** (kualitatif) | Alur multimodal pada data Indonesia | 4 kombinasi spreadsheet + Drive 1 (bagian 8) | tabel kasus |
| **L4 Mode adaptif F2** (eksploratori) | Akuisisi atribut baru menjadi baris kanonik, penyatuan makna, penggunaan ulang | Harness pada API dan database terpisah dengan `KMS_DYNAMIC_SCHEMA` hidup (bagian 14) | ukuran F2 |

**Alasan L1 di samping UI.** Paper umumnya menuntut baseline, ablasi, dan pengulangan yang terkontrol. UI tidak menyediakan mode retrieval-saja atau LLM-saja,
tidak dapat diulang otomatis, dan menyimpan hasil hanya di sesi browser. L1 memakai **kode dan model yang sama persis** dengan UI sehingga skornya sahih untuk sistem
yang sama; L2 memperlihatkan bahwa jalur UI konsisten dengan L1.

**Varian pembanding**

| Kode | Varian | Cara memperoleh | Lapis |
|---|---|---|---|
| S4 | Sistem penuh (retrieval + rerank LLM + verifier) | kolom *proposed_target_canonical_key* | L1, L2 |
| S1 | Exact-name saja | kunci hanya bila *mapping_method* = exact_name; selain itu kosong | turunan dari run S4 |
| S2 | Retrieval top-1 tanpa LLM | kolom `retrieval_s2_key` dari harness: hit teratas retrieval produksi yang direkam untuk setiap atribut (atribut exact_name memakai kunci exact) | hanya L1; UI tidak menampilkannya. Berlaku sebagai baseline yang selalu memetakan (tidak punya opsi NULL) |
| S3 | LLM saja tanpa retrieval | aproksimasi lewat opsi `--s3` di harness (penilai melihat seluruh 60 baris; kode produksi tidak diubah); hasil di HASIL_SEMENTARA bagian 12 | tambahan L1 (dataset atribut) |
| V3 | Fusi tiga sinyal | tindakan fusi dari status dan alasan | L1, L2 |
| V1 | Hanya gambar | status VLM mentah | turunan |
| V2 | Hanya nama file | dihitung luring terhadap daftar varietas terdaftar | turunan, tanpa model |

Bila S3 tidak sempat dibangun, ditulis sebagai keterbatasan; S1, S2, S4 sudah memberi ablasi bertingkat (tanpa semantik, retrieval saja, sistem penuh).

---

## 3. Data, partisi pengembangan vs uji, dan kebocoran

### 3.1 Himpunan data (ringkas; hash dan asal: `data_evaluasi/README_DATA_EVALUASI.md`)

| ID | Berkas | Butir | Bertarget | Tanpa target | Status |
|---|---|---|---|---|---|
| R01 | `data_input.xlsx` | 14 | 1 | 13 | **Dev** (dipakai pada kampanye anotasi pilot dan pengujian) |
| S01 | `D01_transposed_indonesia_mixed.xlsx` | 21 | 20 | 1 | **Dev** (alias sistem ditambahkan setelah melihat label ini) |
| S02 | `D02_row_flat_english_semantic.xlsx` | 26 | 22 | 4 | **Dev** (idem) |
| S03 | `D03_row_multilevel_indonesia.xlsx` | 30 | 28 | 2 | Dev (fixture pengujian parser) |
| S04 | `D04_varietas_kosong_invalid.xlsx` | 8 | 6 | 2 | Dev (fixture) |
| R02 | `input_cabai_kms.xlsx` | 54 | 18 | 32 | **Held-out** |
| N07 | `E07_kementan_deskripsi_ext.xlsx` | 70 | 20 | 45 | **Held-out** |
| N08 | `E08_zenodo_capsicum_en.xlsx` | 23 | 9 | 12 | **Held-out** |
| N09 | `dataset_cabai_deskripsi_varietas.xlsx` | 80 | 24 | 48 | **Held-out** |

Total 326 butir. Skor utama dilaporkan untuk **kelompok held-out (R02, N07, N08, N09)** dan terpisah untuk kelompok dev (R01, S01 sampai S04).
Klaim kesimpulan utama hanya bertumpu pada held-out. Kelompok dev dipakai untuk menunjukkan ketahanan struktur dan bahasa, dan tidak boleh dikutip sebagai bukti generalisasi.

### 3.2 Bukti kebocoran dan stratifikasi kesulitan (diukur 31 Okt 2026)

`src/schema/row_aliases.yaml` (alias manual, 28 entri) dan label kanonik membuat sebagian atribut dapat dijawab hanya dengan pencarian:

| Kelompok | Butir bertarget | Cocok label kanonik persis | Cocok alias terdaftar (kunci benar) |
|---|---|---|---|
| Held-out (R02, N07, N08, N09) | 71 | 29 | 3 |
| Dev (R01, S01 sampai S04) | 77 | 2 | 3 |
| Total | 148 | 31 | 6 |

Artinya 37 dari 148 butir bertarget (25%) dapat diselesaikan lookup; 111 butir memerlukan penalaran semantik. Alias yang cocok pada S01 ("Bentuk pertumbuhan tanaman", "Warna dominan daun")
dan pada S02 ("vertical height at maturity" sebagai varian dari "Vertical size at maturity") menunjukkan alias ditambahkan setelah melihat data dev. Aturan:

1. **Bekukan alias** pada `row_aliases.yaml` saat ini; tidak boleh menambah alias selama dan sesudah eksperimen tanpa mencatat deviasi.
2. Laporkan hasil juga **per stratum kesulitan**: (a) butir yang diselesaikan lookup (exact label atau alias), (b) butir yang memerlukan semantik.
3. Foto (E3) tidak memakai data pengembangan; foto Commons dikumpulkan setelah sistem dibangun.

---

## 4. Gold dan kualitas anotasi

| Aspek | Standar | Kondisi dan tindakan |
|---|---|---|
| Jumlah anotator | Minimal dua, independen, buta | **Belum tercapai.** Yang dilakukan: gold atribut **diverifikasi butir per butir oleh penulis** (`gold/final/gold_semua_dataset_final.csv`, sumber `terverifikasi_v1`). Template buta dua anotator tetap tersedia di `data_evaluasi/anotasi_buta/` bila anotator tambahan ada |
| Kesepakatan | Cohen's kappa (status) dan persentase kunci sama | Dihitung setelah A dan B selesai; dilaporkan |
| Adjudikasi | Perselisihan diselesaikan pihak ketiga (pembimbing) atau konsensus tercatat | Gold final = hasil adjudikasi |
| Usulan awal | Hanya draf | `gold_semua_dataset.csv` dipertahankan sebagai pembanding |
| Foto | Label diverifikasi dua penilai buta | **Belum.** Gold foto diverifikasi satu per satu oleh penulis (`gambar/manifest/gold_gambar_manifest_final.csv`, `gold_foto_pvt_317.csv`, sumber `terverifikasi_v1`); bukan verifikasi ahli. Template buta tetap tersedia |
| Pedoman | Tertulis dan dibekukan | `docs/annotation_guidelines_v1.md` dan `docs/HUMAN_ANNOTATION_GUIDE.md` |

Perkiraan beban: sekitar 1 sampai 2 jam per anotator untuk 326 butir; sekitar 30 menit untuk 160 foto. **Sampai gold dua anotator selesai, semua skor dilabeli "terhadap gold yang diverifikasi penulis".**

---

## 5. Prosedur pelaksanaan

### 5.1 Pembekuan dan pencatatan
- Commit acuan tiap eksperimen: tabel di awal dokumen. Commit terkini `060b29f` (= `24e1037` + D1, D2, D5, D6, katalog atribut D7, perbaikan draf D8, skema dinamis D9a sampai D9c; bagian 12); model teks `ag/gemini-3.8-flash-medium`, vision `ag/gemini-3.8-flash-high` (via 9Router); `k = 8`; backend retrieval `chroma`. Tidak ada deploy, perubahan `.env` atau kode, atau penggantian model selama eksperimen.
- Catat per run: tanggal-jam, commit, model, `evaluation_config_fingerprint` (dari keluaran), SHA-256 berkas, tautan Drive, durasi, galat.
- Sebelum run pertama, hash protokol ini dicatat (`sha256sum docs/SKENARIO_EKSPERIMEN.md`); deviasi dicatat pada bagian 12.

### 5.2 Urutan dan pengulangan
- **Urutan run diacak** (seed 20261031) untuk mengurangi pengaruh pergeseran waktu pada layanan model.
- **L1 atribut:** 9 workbook x **3 pengulangan**; laporkan rata-rata dan simpangan baku antar pengulangan.
- **L1 foto:** 160 foto x 1 pengulangan, ditambah 3 pengulangan pada subset 40 foto (stratified) untuk menaksir variasi.
- **L2 (UI) dan L3:** satu kali.
- **Realisasi:** harness atribut 3 pengulangan terlaksana; harness foto kombinasi S01 sampai S03 4 pengulangan (satu dari format lama); UI terlaksana sekali; urutan UI mengikuti `INSTRUKSI_JARVIS_EKSPERIMEN_UI.txt`, dan harness foto Commons tidak dijalankan (hanya UI).
- Satu percobaan ulang hanya untuk galat jaringan; jawaban yang dianggap salah tidak diulang.

### 5.3 Keselamatan operasional
Eksperimen menulis ke database live (kandidat dan media). Backup database sebelum mulai; jangan Commit atau Terapkan Koreksi; bersihkan kandidat uji sesudahnya.
UI publik tanpa login selama eksperimen. Rahasia tidak boleh masuk laporan.

---

## 6. Metrik dan statistik

**Metrik inti (empat):** Mapping F1 (P, R), recall atribut baru, macro-F1 foto tiga kelas, Top-1 pada KNOWN. Definisi di `RENCANA_EVALUASI.md`.

**Dua mode evaluasi.** *Mode beku* (saklar `KMS_DYNAMIC_SCHEMA` mati; 60 baris kanonik tetap) adalah satu-satunya mode untuk skor inti dan semua perbandingan varian. *Mode adaptif* (saklar hidup) dievaluasi
terpisah dengan ukuran F2 (bagian 14). Recall atribut baru hanya bermakna pada mode beku, karena pada mode adaptif atribut tanpa padanan sengaja dijadikan baris baru.

**Statistik:**
- CI 95% bootstrap (1000 ulangan, seed 20261029) untuk tiap skor; untuk uji perbandingan memakai **paired bootstrap 10.000 ulangan** atas butir/foto yang sama.
- Perbandingan yang diuji sebelumnya (confirmatory): S4 vs S1, S4 vs S2 (Mapping F1); V3 vs V1 (macro-F1) dan V3 vs V2 pada kondisi MENYESATKAN. **Koreksi Holm** untuk semua perbandingan itu. Perbandingan lain bersifat eksploratori dan ditandai begitu.
- Laporkan **ukuran efek** (selisih F1 dengan CI), bukan hanya p.
- **Variasi model:** simpangan baku antar tiga pengulangan; bila selisih antar varian lebih kecil dari variasi itu, tidak diklaim sebagai perbedaan.
- Kualitas gold: Cohen's kappa antar anotator (atribut dan foto).
- Aturan skor: AMBIGUOUS (16) dan COMPOSITE (3) dikeluarkan dari skor inti dan dilaporkan terpisah; prediksi gagal dihitung sebagai prediksi kosong (atribut) atau UNCERTAIN (foto); jumlahnya dilaporkan.
- Ambang keyakinan foto dipilih **hanya pada split val** (52 foto), dibekukan, lalu dilaporkan pada split test (108 foto).

Pelaporan terpisah: held-out vs dev; stratum lookup vs semantik; kondisi nama file (NETRAL, INFORMATIF, MENYESATKAN); n disebut pada tiap sel; kelas foto kecil tidak dilaporkan per kelas.

---

## 7. Lingkungan

| Item | Nilai |
|---|---|
| UI | https://cabai.rifqisetiawan.my.id/KMS (Caddy ke `127.0.0.1:8501`; tanpa login) |
| Host | `4.240.9.128`; akses `ssh myvps`; root `sudo -i` |
| Repo | `/srv/hermes-control/services/agentic-ai-cabai-kms`, `main` = `01e2d08` (sebelumnya `24e1037`; lihat bagian 12; rollback `1306fbf`); sudah di-push ke `origin/main` pada 1 November 2026 (11 commit, `24e1037..01e2d08`) |
| Layanan | `cabai-kms.service` (UI), `cabai-kms-api.service` (8093) |
| DB | PostgreSQL `cabai_kms`, role `cabai_app`; migrasi 0001 sampai 0007 (0006 katalog atribut, 0007 baris skema dinamis); database uji `cabai_kms_test` dan `cabai_kms_eval` (terpisah, boleh dihapus) |
| Model | 9Router `127.0.0.1:20128`; preflight `scripts/ninerouter_preflight` |
| Input di VPS | `/srv/hermes-control/eval/cabai-ui-experiment/inputs/` (10 workbook, SHA-256 identik dengan laptop); hasil: `.../hasil_ui/` |
| Gold | **tidak ada di VPS** (pelaksana tidak boleh melihat gold) |

Batasan UI (dari kode): maks 20 foto per run, sekitar 20 sampai 50 detik per foto; hasil hanya di sesi browser (unduh sebelum pindah); tabel Inspektor pemetaan dan Hasil multimodal dapat diunduh CSV;
workbook hasil dapat diunduh; jangan menekan Terapkan Koreksi.

---

## 8. Skema run lewat UI (L2 dan L3)

Link Drive 1: https://drive.google.com/drive/folders/1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g?usp=drive_link (12 foto peneliti).
Link Drive 2 (160 foto, datar; arsip): https://drive.google.com/drive/folders/1V3gIAOG-wDeZP8o9LUE1KEJ2moCSWthA?usp=drive_link.
Untuk batas 20 foto per run, 160 foto dibagi 8 folder F1 sampai F8 (`gambar/foto_commons_8_folder.zip`; pembagian: `gambar/manifest/pembagian_8_folder.csv`); folder F1..F8 sudah dibuat (induk `1wcTPSuNbLys96h3xGt50H9S4bInl8-1h`; 20 foto per folder, cocok manifest).
Akses semua folder lewat service account `finance-hub-bot@personal-finance-hub-509103.iam.gserviceaccount.com` (Viewer).

**Bagian A: atribut saja (tanpa Drive)** — gold: berkas gold per dataset di `data_evaluasi/gold/`

| Run | Workbook | Sheet | Format | Header | Gold pembanding | Butir |
|---|---|---|---|---|---|---|
| 1 | `data_input.xlsx` (R01) | Resume Data | row-oriented | Otomatis | `gold_R01_data_input.xlsx` | 14 |
| 2 | `input_cabai_kms.xlsx` (R02) | Data Varietas | row-oriented | 1 baris | `gold_R02_input_cabai_kms.xlsx` | 54 |
| 3 | `E07_kementan_deskripsi_ext.xlsx` (N07) | Deskripsi Varietas | row-oriented | 1 baris | `gold_N07_E07_...xlsx` | 70 |
| 4 | `E08_zenodo_capsicum_en.xlsx` (N08) | Observed85_readable | row-oriented | 1 baris | `gold_N08_E08_...xlsx` | 23 |
| 5 | `dataset_cabai_deskripsi_varietas.xlsx` (N09) | transposed | transposed | - | `gold_N09_dataset_...xlsx` | 80 |

**Bagian B: spreadsheet + Drive 1 (multimodal Indonesia; atribut dan foto sekaligus)**

| Run | Workbook | Link Drive | Gold atribut | Gold foto (turunan) |
|---|---|---|---|---|
| 6 | `D01_transposed_indonesia_mixed.xlsx` (S01) | Drive 1, max 12 | `gold_S01_D01_...xlsx` (21) | `gambar_id/gold_kombinasi_drive1.csv`, spreadsheet = S01 |
| 7 | `D02_row_flat_english_semantic.xlsx` (S02) | Drive 1, max 12 | `gold_S02_D02_...xlsx` (26) | idem, spreadsheet = S02 |
| 8 | `D03_row_multilevel_indonesia.xlsx` (S03) | Drive 1, max 12 | `gold_S03_D03_...xlsx` (30) | idem, spreadsheet = S03 |
| 9 | `D04_varietas_kosong_invalid.xlsx` (S04) | Drive 1, max 12 | `gold_S04_D04_...xlsx` (8) | idem, spreadsheet = S04 |

Foto yang sama (Domba, Katokkon, Kopay, Gendot) berganti status KNOWN atau OTHER menurut varietas pada spreadsheetnya: S01 dan S02 (6 KNOWN, 2 OTHER, 2 UNCERTAIN), S03 (6 KNOWN, 2 OTHER, 2 UNCERTAIN), S04 (2 KNOWN, 6 OTHER, 2 UNCERTAIN).
Hanya 10 foto per kombinasi yang dinilai (dua foto tidak layak: gambar stok dan tanpa label); **hasilnya disajikan sebagai tabel kasus, bukan F1**.
Catatan: label foto peneliti berasal dari nama berkas; foto daun, bunga, dan tangkai tidak dapat dibedakan varietasnya dari gambar (kolom `dapat_dibedakan_dari_gambar`), jadi sistem yang menahan keputusan (UNCERTAIN) pada foto itu tidak otomatis salah.

**Bagian C: foto Commons (E3, skor kuantitatif foto) — workbook varietas terdaftar**

| Run | Workbook | Link Drive | Gold pembanding | Foto |
|---|---|---|---|---|
| 10 sampai 17 | `spreadsheet_varietas_terdaftar.xlsx` (sheet Data Varietas, row-oriented, header Otomatis) | folder F1 sampai F8, max 20 (selesai dijalankan 1 November 2026) | baris folder itu di `gambar/manifest/gold_gambar_manifest.csv` | 20 per run |

**Mengapa 160 foto Commons:** foto adalah input untuk menguji klasifikasi gambar; tiap foto punya label benar (KNOWN 99, OTHER 45, UNCERTAIN 16) sehingga macro-F1 dan Top-1 dapat dihitung dengan n yang memadai.
Foto ini **proksi luar negeri**: foto cabai Indonesia berlabel andal tidak tersedia (iNaturalist: label tidak andal; PDF Kementan: tidak memuat foto varietas). Workbook 8 varietas hanya memberi sistem daftar varietas terdaftar;
ia pembantu, bukan data penelitian, dan tidak dihitung dalam skor atribut. Total L2 dan L3: 17 run.

**Langkah satu run dan penyimpanan hasil** (tidak berubah dari versi 3; lengkap pada `INSTRUKSI_JARVIS_EKSPERIMEN_UI.txt`): unggah workbook, pilih sheet, format, header, isi tautan Drive dan batas foto,
Jalankan Pipeline, lalu sebelum apa pun: tangkapan layar Ringkasan run, unduh CSV Inspektor pemetaan (`mapping.csv`) dan Hasil multimodal (`vision.csv`), unduh workbook hasil asli, tulis satu baris RUNLOG.
Struktur: `hasil_ui/<tanggal>/{atribut/<ID>,kombinasi/<ID>,gambar/F<n>}/`.

**Siapa yang menjalankan:** Jarvis (Hermes) lewat Telegram bila ia dapat mengendalikan browser; **belum diverifikasi**. Pelaksana tidak diberi gold. Claude tidak dapat menjalankan UI saat ini
(tidak ada ekstensi Chrome; tabel Streamlit di kanvas). L1 (harness) dijalankan di VPS oleh Jarvis atau Rifqi dengan perintah pada bagian 5; Claude menganalisis keluaran.

---

## 9. Ancaman terhadap validitas

| Jenis | Ancaman | Mitigasi |
|---|---|---|
| Internal | Kebocoran alias dari data dev ke uji | Partisi dev vs held-out; alias dibekukan; stratum lookup vs semantik |
| Internal | Nondeterminisme model dan layanan | Konfigurasi beku; 3 pengulangan; urutan acak; sebut simpangan baku |
| Internal | Pelaksana mempengaruhi hasil | Pelaksana buta terhadap gold; protokol tertulis; deviasi dicatat |
| Konstruk | Gold atribut diverifikasi satu penulis | Dinyatakan di metodologi; periksa butir prioritas sebelum sidang; dua anotator bila tersedia |
| Konstruk | Gold foto dari label komunitas Commons, diverifikasi penulis | Dinyatakan; banyak keputusan bertumpu pada label sumber; kelas kecil tidak dilaporkan per kelas |
| Internal | Mode adaptif memengaruhi pemetaan template | Saklar mati bawaan; regresi identik; F2-4 mengukur selisih F1 template |
| Internal | Hasil mode adaptif bergantung pada urutan run | Urutan dicatat; tiga pengulangan dari database kosong (F2-5) |
| Konstruk | Foto proksi luar negeri | Dinyatakan; L3 menyajikan foto Indonesia secara kualitatif |
| Eksternal | Hanya 9 workbook dan satu bidang (cabai) | Sebut cakupan; jangan generalisasi ke domain lain |
| Eksternal | Penulisan dokumen KMS hanya untuk tata letak Resume Data (keputusan opsi A, 1 Nov 2026) | Nyatakan sebagai batasan masalah; klaim standardisasi lintas format dibatasi pada pemetaan dan Excel kanonik |
| Eksternal | 25% butir terselesaikan lookup | Laporkan stratum |
| Kesimpulan | n kecil, CI lebar | Paired bootstrap, ukuran efek, Holm; klaim hati-hati |
| Kesimpulan | Banyak perbandingan | Confirmatory ditetapkan di muka; sisanya eksploratori |

---

## 10. Reproduksibilitas, etika, dan lisensi

- Paket rilis: commit kode, ID model, `evaluation_config_fingerprint`, RUNLOG, berkas input (hash), gold final (setelah adjudikasi), skrip konversi dan hitung metrik, seed.
- **Datasheet dataset** (asal, tujuan, komposisi, pelabelan, batasan, lisensi) untuk gold atribut dan foto.
- Lisensi: workbook Zenodo CC BY 4.0 (atribusi pengarang); deskripsi Kementan dokumen publik pemerintah (syarat pakai ulang belum diperiksa); foto Commons CC0, CC BY, CC BY-SA (`manifest/ATRIBUSI_LISENSI.csv`);
  foto peneliti: satu berwatermark media sosial dan satu gambar stok, hak ciptanya dicek sebelum dimuat; iNaturalist berlisensi terbuka, tidak dipakai untuk skor.
- Tidak ada data pribadi; foto yang memuat orang sudah dibuang. Rahasia (token, `.env`) tidak dicantumkan.
- Penggunaan model komersial (9Router) dan potensi bias model dinyatakan sebagai keterbatasan.

---

## 11. Jadwal, prasyarat, dan daftar periksa

| Tahap | Kegiatan | Penanggung jawab | Status |
|---|---|---|---|
| T0 | Bekukan protokol ini (hash); tentukan dua anotator manusia | Rifqi | protokol tidak di-hash formal; deviasi D1 sampai D9c tercatat; anotator manusia belum |
| T1 | Anotasi gold atribut dan foto | Penulis | selesai, diverifikasi penulis (bagian 4); dua anotator independen belum |
| T2 | Pilot: run 6 (D01 + Drive 1); konfirmasi unduhan CSV dan waktu | Jarvis/Rifqi | selesai (setelah D5) |
| T3 | L1 harness: atribut x3, foto kombinasi x4 | Claude/VPS | selesai; foto Commons hanya lewat UI |
| T4 | L2 UI: 17 run | Jarvis | selesai (S04 dan N08 asli ditolak sistem) |
| T5 | Analisis: konversi, metrik, uji signifikan, tabel, analisis kesalahan | Claude | selesai untuk eksperimen inti (`HASIL_SEMENTARA_EKSPERIMEN.md`); F2 menyusul |
| T5b | Eksperimen F2 (bagian 14) | Claude/VPS | berjalan |
| T6 | Pembersihan DB (kandidat uji), arsip hasil, datasheet, paket rilis | Rifqi | arsip hasil lokal ada di `data_evaluasi/hasil_eksperimen/`; pembersihan antrean kandidat (36) belum; commit sudah di-push |

Daftar periksa (status 1 November 2026): [ ] protokol di-hash; [ ] dua anotator manusia; [x] backup DB (sebelum migrasi 0006 dan 0007); [x] 8 folder Drive dibuat dan diuji 20 foto per folder;
[x] alias dibekukan; [x] gold final terverifikasi; [x] Jarvis mengendalikan browser lewat CDP; [ ] antrean kandidat foto dikosongkan; [x] commit di-push ke GitHub (`01e2d08`).

---

## 12. Log deviasi

| # | Tanggal | Perubahan | Alasan | Dampak |
|---|---|---|---|---|
| D1 | 2026-10-31 (sebelum run eksperimen pertama) | Commit `0f0fbca` di atas `24e1037`: tambah `from sqlalchemy.orm import Session` di `src/kms_api/app.py`; restart `cabai-kms-api` | `GET /discarded` mengembalikan HTTP 500 (`NameError: Session`), sehingga semua run dengan foto Drive gagal, di UI maupun harness | Hanya jalur pengecekan foto yang pernah dibuang; tidak menyentuh pemetaan atribut, retrieval, atau model. Diverifikasi: run S01 + Drive 1 di harness selesai (12 foto diproses) |
| D2 | 2026-10-31 (setelah pilot S01 UI) | Commit `3225a92` di atas `0f0fbca`: `src/integrations/candidates_ui.py` mengambil bytes gambar kandidat lewat `KmsClient` (`/media/{asset_id}/image`); restart `cabai-kms.service` | Halaman KMS error `MediaFileStorageError` karena `media_url` (`/media/<id>`) diteruskan ke `st.image` sebagai path lokal | Hanya tampilan panel kandidat; pipeline tidak berubah. 51 tes kandidat lulus; gambar nyata berhasil diambil. Pilot S01 UI harus diulang pada commit ini |
| D3 | 2026-10-31 | Efek samping uji harness: 12 kandidat tertulis ke `kms.image_candidates` (17:33-17:38 WIB) | `POST /candidates` dipanggil pipeline foto; `write_applied=False` bukan jaminan tidak menulis DB | DB kandidat harus direset ke keadaan awal sebelum tiap run foto agar run independen; menunggu keputusan penghapusan |
| D4 | 2026-10-31 | Run tambahan N08 dengan `E08_zenodo_capsicum_en_variety.xlsx` (SHA-256 `6ede08a0...3b0a`): hanya sel A1 diganti dari `Genotype name` ke `Variety` | Parser menolak workbook asli (`Kolom varietas tidak ditemukan`) pada 3 dari 3 pengulangan | Hasil asli dilaporkan sebagai kegagalan sistem pada format yang tidak dikenal; hasil varian dilaporkan terpisah dan ditandai preprocessing. Nilai dan gold tidak berubah |
| D5 | 2026-10-31 | Commit `323f1e4` di atas `3225a92`: `src/ui/pages/3_Hasil.py` menambah dua tombol `st.download_button` (pemetaan lengkap CSV; hasil multimodal lengkap CSV); restart `cabai-kms.service` | Ekspor CSV toolbar tabel memakai `showSaveFilePicker` dan tidak menghasilkan unduhan di Chrome headless (pilot S01 UI gagal dua kali) | Hanya penyajian ekspor; pipeline tidak berubah. Ekspor memuat semua kolom (superset kolom tabel). 25 tes `test_ui.py` lulus. Hasil UI sebelum D5 tidak dicampur |
| D6 | 2026-10-31 (setelah batch A/B pada `323f1e4`) | Commit `bc3c21b` di atas `323f1e4`: `src/integrations/vision_hook.py`, deteksi varietas run dari header output memakai `"karakter"` (sebelumnya `"karakteristik"`); restart `cabai-kms.service` | Header output template berbunyi `Karakter`, sehingga `extract_run_scope_varieties` selalu `[]`; klasifier foto tidak pernah menerima daftar varietas spreadsheet dan semua foto jatuh ke CANDIDATE (12/12 pada S01, S02, S03; skor 2/10 per kombinasi) | Hanya jalur foto. Hasil foto kombinasi pada `323f1e4` dan `3225a92` TIDAK dipakai sebagai hasil (disimpan sebagai `kombinasi_323f1e4_pra_D6`); run kombinasi S01-S03 diulang pada `bc3c21b`. Hasil atribut tidak terpengaruh (jalur kode tidak dipakai tanpa Drive) dan tetap sah; 141 tes lulus |
| D7 | 2026-11-01 | Commit `a16c5cc` di atas `bc3c21b`: migrasi `0006` (katalog atribut persisten, tabel append-only), aksi kurator `REGISTER_NEW`/`MAP_TO_EXISTING`/`REJECT` untuk review NEW_ATTRIBUTE, planner memuat katalog persisten, API `GET /attributes/catalog`, UI kurator; restart `cabai-kms-api` dan `cabai-kms` | Atribut baru yang disetujui kurator sebelumnya hilang setelah review (tidak terdaftar dan tidak ditulis ke dokumen) | Hanya jalur penyimpanan dan kurasi KMS; `pipeline_runner`, `vision_hook`, dan template (60 baris) tidak diubah (diff 8 berkas). Regresi harness pada `a16c5cc`: R01 kunci identik di 13/13 atribut terhadap 3 pengulangan lama; N09 Mapping F1 1,000 sama dengan 3 pengulangan lama, kunci identik 78/80 (dua butir bergeser, sebesar variasi antar pengulangan lama sendiri: pengulangan 1 dan 2 lama berbeda satu butir). Kriteria regresi direvisi: hasil lama tetap berlaku bila skor sama dan perbedaan butir tidak melebihi variasi antar pengulangan lama. Backup DB sebelum migrasi: `backup_cabai_kms_sebelum_0006.dump` |
| D8 | 2026-11-01 | Commit `27e68bc` di atas `a16c5cc`: `src/integrations/streamlit_commit.py` (`get_or_create_draft`), `src/ui/app.py` (menyimpan byte workbook di sesi, membersihkan draf lama saat run baru); restart `cabai-kms` | Draf dokumen KMS tidak berasal dari workbook run: berkas unggahan hanya berupa berkas sementara yang dihapus, sehingga draf diambil dari `data/samples/data_input.xlsx` atau draf placeholder buatan, dan di-cache lintas run | Hanya panel review dan commit KMS di halaman Hasil; pemetaan, klasifikasi foto, dan keluaran (CSV, Excel) tidak berubah, jadi hasil eksperimen tidak terpengaruh. Seluruh suite tes lulus (1248). Layout yang tidak didukung kini dilaporkan, bukan diganti |
| D9a | 2026-11-01 | Commit di atas `27e68bc`: infrastruktur skema kanonik dinamis tahap 1 (migrasi `0007`, `SchemaRowRepository`, API `/attributes/schema-rows`, `src/schema/dynamic.py`, koleksi Chroma per skema, baris akuisisi di keluaran Excel, skema run dibawa di state pipeline); backup DB `backup_cabai_kms_sebelum_0007.dump`; restart API dan UI | Fase 2: atribut baru menjadi baris kanonik (rancangan `RANCANGAN_KANONIK_DINAMIS.md`) | Saklar `KMS_DYNAMIC_SCHEMA` mati secara bawaan. Regresi saklar mati pada R01: kunci pemetaan identik 13/13, fingerprint identik, Excel identik (61 baris, 0 sel berbeda). 1257 tes lulus |
| D9b | 2026-11-01 | Commit `a5ebdb9` di atas `b7b38e3`: akuisisi atribut tanpa padanan sebagai baris kanonik baru (`src/agents/schema_matching/acquisition.py`, integrasi di `pipeline_runner`, alias pada `SchemaRowRepository`); restart API dan UI | Fase 2 tahap 2: atribut baru menjadi baris kanonik, tanpa duplikat makna | Saklar `KMS_DYNAMIC_SCHEMA` mati bawaan. Regresi saklar mati (R01): kunci pemetaan identik, 38 kolom sama, fingerprint identik, Excel identik (61 baris, 0 sel berbeda); 1264 tes lulus. Uji saklar hidup pada API dan DB terpisah (`cabai_kms_eval`): lihat HASIL_SEMENTARA bagian 8 |
| D9c | 2026-11-01 | Commit `060b29f` di atas `a5ebdb9`: id baris akuisisi mengikuti nomor urut tersimpan; penggabungan menjadi alias; aksi setujui, buang, gabung di API; panel kurator di halaman KMS | Fase 2 tahap 3: kurasi baris provisional | Saklar mati bawaan. Regresi saklar mati (R01): kunci, fingerprint, dan Excel identik; 1270 tes lulus |
| D9d | 2026-11-01 (setelah F2 versi 1) | Commit `3705aab` di atas `060b29f`: penilai akuisisi menerima daftar seluruh baris yang ada dan aturan makna sama yang lebih ketat; atribut berstatus duplikat ditulis ke baris yang ada (`MERGED_TO`) | F2 versi 1 menemukan baris akuisisi yang menggandakan baris template (`warna mahkota bunga`) dan merebut pemetaan template (F1 -0,02), serta duplikat yang tidak ditulis | Hanya jalur akuisisi (saklar hidup). Saklar mati: regresi R01 identik (kunci, fingerprint, Excel), 1272 tes lulus. F2 diulang sebagai versi 2; hasil versi 1 tetap dilaporkan |
| D9e | 2026-11-01 (setelah F2 versi 2) | Commit `6217420` di atas `3705aab`: penilai akuisisi menilai kandidat dalam batch 12 dengan percobaan ulang 3 kali, baris yang baru diakuisisi ditambahkan ke daftar batch berikutnya, alasan dibatasi satu kalimat pendek, pesan galat dicatat | F2 versi 2: satu panggilan untuk sampai 55 atribut memakan 2 sampai 3 menit dan kehabisan waktu pada 5 dari 12 run (akuisisi dilewati) | Hanya jalur akuisisi (saklar hidup). Saklar mati: regresi R01 identik, 1274 tes lulus. F2 diulang sebagai versi 3; hasil versi 2 dilaporkan dengan catatan bahwa lima run tidak sah |
| D10 | 2026-11-02 (setelah uji UI produksi dengan saklar aktif) | Commit `8d89e06` di atas `6217420`: atribut kandidat akuisisi tidak lagi dimasukkan ke antrean review sebelum akuisisi; hanya yang akhirnya tanpa baris yang masuk antrean | Uji UI produksi: halaman Hasil menampilkan 11 review belum selesai padahal REVIEW 3, karena 8 atribut yang kemudian diakuisisi tetap pending | Hanya antrean review pada mode saklar hidup; tidak memengaruhi hasil F2 (harness tidak membaca antrean) dan tidak berubah pada saklar mati (regresi R01 identik: kunci dan status sama, 38 kolom; 1276 tes lulus) |

Setiap perubahan lain setelah pembekuan dicatat di tabel ini dengan tanggal, alasan, dan dampak.

---

## 13. Lampiran

| Item | Lokasi |
|---|---|
| Metrik | `docs/RENCANA_EVALUASI.md` |
| Data, gold, hash | `data_evaluasi/README_DATA_EVALUASI.md`, `data_evaluasi/gold/` |
| Template anotasi buta | `data_evaluasi/anotasi_buta/` |
| Foto Commons, pembagian 8 folder | `data_evaluasi/gambar/README_GAMBAR.md`, `manifest/pembagian_8_folder.csv`, `foto_commons_8_folder.zip` |
| Foto Indonesia dan gold kombinasi | `data_evaluasi/gambar_id/`, `gold_kombinasi_drive1.csv` |
| Skrip | `data_evaluasi/skrip/`: `konversi_ui.py`, `hitung_metrik.py`, `harness_vps.py`, `analisis_lanjut.py`, `eval_atribut_baru.py`, `analisis_kanonik_dinamis.py`, `buat_lembar_verifikasi.py`, `terapkan_verifikasi.py`, `arsipkan_hasil.sh` |
| Gold final | `gold/final/gold_semua_dataset_final.csv`, `gambar/manifest/gold_gambar_manifest_final.csv`, `verifikasi_gold/` |
| Hasil mentah dan arsip | `data_evaluasi/hasil_eksperimen/` (`README.md`, `SHA256SUMS_lokal.txt`) |
| Rancangan fitur | `docs/RANCANGAN_ATRIBUT_BARU.md` (fase 1), `docs/RANCANGAN_KANONIK_DINAMIS.md` (fase 2) |
| Instruksi pelaksana UI | `INSTRUKSI_JARVIS_EKSPERIMEN_UI.txt` (versi 17 run, commit `bc3c21b`) |

---

## 14. Protokol F2: skema kanonik dinamis (mode adaptif)

**Tujuan:** menunjukkan bahwa atribut di luar kanonik dapat diakuisisi menjadi baris kanonik, disatukan menurut makna, dan dipakai ulang, tanpa merusak pemetaan ke baris template.

**Konfigurasi:** `KMS_DYNAMIC_SCHEMA=true`; API KMS terpisah pada port 18095 dengan database `cabai_kms_eval` (dibuat ulang dari kosong di awal tiap pengulangan, migrasi 0001 sampai 0007); model teks produksi; commit `060b29f`.
**Urutan dataset per pengulangan:** R01, N07, N09, R02 (harness `--ordered`). **Pengulangan:** 3. Skrip: `skrip/analisis_kanonik_dinamis.py`.

| Uji | Ukuran | Pembanding |
|---|---|---|
| F2-1 akuisisi | kandidat dinilai, baris baru, ditolak sebagai bukan karakter, duplikat dari baris ada, gagal; baris Excel | baris template 60 |
| F2-2 penggunaan ulang | atribut dipetakan ke baris akuisisi lama pada dataset berikutnya | dataset pertama (tanpa baris lama) |
| F2-3 anti duplikat | baris dibanding kandidat; pasangan label dengan kemiripan tinggi (tinjauan kurator) | jumlah baris bila tanpa penyatuan |
| F2-4 keamanan | Mapping F1 baris template mode adaptif (baris akuisisi diabaikan; dan versi ketat) | mode beku, harness pengulangan 1 |
| F2-5 stabilitas | jumlah baris dan kemiripan label (Jaccard) antar pengulangan | antar pengulangan |

**Aturan pelaporan:** hanya mode adaptif; tidak masuk skor inti atau koreksi Holm. Kualitas tiap baris (apakah karakter tanaman yang sah) ditinjau manual dan dilabeli hasil tinjauan model sampai diverifikasi peneliti.
**Hasil:** `docs/HASIL_SEMENTARA_EKSPERIMEN.md` bagian 8 sampai 11 (versi 1 `urutan_A`, versi 2 `urutan_B` sebagian tidak sah, versi 3 `urutan_C` dipakai untuk klaim); data mentah `hasil_eksperimen/hasil_dinamis/`.

