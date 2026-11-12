# Rencana Evaluasi CABAI-KMS (metrik inti dan ukuran F2)

Versi 4, 1 November 2026. Dokumen ini memuat definisi metrik, dua mode evaluasi, ukuran untuk fitur skema dinamis (F2), dan aturan statistik. Hipotesis, desain, partisi dev/held-out,
skenario run, log deviasi, dan jadwal ada di `docs/SKENARIO_EKSPERIMEN.md` (v4, diperbarui); hasil sementara di `docs/HASIL_SEMENTARA_EKSPERIMEN.md`; data dan gold di `data_evaluasi/`.

Evaluasi menilai **keluaran akhir sistem**: kunci kanonik yang diusulkan untuk tiap atribut dan status klasifikasi tiap foto.
Pembagian jalur review manusia (otomatis atau review) tidak dijadikan metrik.

## 1. Empat metrik inti (mode beku)

| # | Komponen | Metrik | Dipakai untuk |
|---|---|---|---|
| 1 | Pemetaan atribut | **Mapping F1** (dengan Precision dan Recall) | Ketepatan pemetaan atribut ke kunci kanonik |
| 2 | Pemetaan atribut | **Recall atribut baru** | Atribut di luar kanonik tidak dipaksa dipetakan |
| 3 | Klasifikasi foto | **Macro-F1 tiga kelas** (KNOWN / OTHER / UNCERTAIN) | Ketepatan status klasifikasi |
| 4 | Klasifikasi foto | **Top-1 accuracy pada KNOWN** | Varietas yang ditautkan benar |

## 2. Dua mode evaluasi

| Mode | Konfigurasi | Dipakai untuk | Metrik |
|---|---|---|---|
| **Beku** | `KMS_DYNAMIC_SCHEMA` mati; 60 baris kanonik tetap | Semua skor inti dan perbandingan varian (S1, S2, S4, V1 sampai V3) | Empat metrik inti, uji signifikansi |
| **Adaptif** | `KMS_DYNAMIC_SCHEMA` hidup; atribut tanpa padanan diakuisisi menjadi baris kanonik tambahan | Evaluasi fitur akuisisi (F2) | Ukuran F2 (bagian 4) |

Aturan: skor inti **tidak pernah** dihitung dari run mode adaptif. **Recall atribut baru hanya bermakna pada mode beku**, karena pada mode adaptif atribut tanpa padanan sengaja dijadikan baris baru; pada mode adaptif
Mapping F1 hanya dilaporkan untuk baris template (lihat F2-4). Dengan saklar mati, keluaran sistem identik dengan sebelum fitur ditambahkan (diverifikasi pada R01: kunci pemetaan, fingerprint, Excel).

## 3. Definisi

Pemetaan atribut. Unit = satu butir atribut pada gold (`data_evaluasi/gold/`; versi final dengan label asal: `gold/final/gold_semua_dataset_final.csv`). Prediksi = kunci kanonik pada kolom *Proposed canonical key*
di tabel Inspektor pemetaan UI atau CSV unduhan, atau "tidak ada pemetaan" bila kosong.

- Butir ONE_TO_ONE = **butir bertarget** (148). Butir NO_MATCH = **butir tanpa target** (159).
- Precision = prediksi berkunci benar / seluruh prediksi berkunci (termasuk yang jatuh pada butir tanpa target).
- Recall = prediksi berkunci benar pada butir bertarget / jumlah butir bertarget.
- **Mapping F1** = 2PR / (P + R).
- **Recall atribut baru** = butir tanpa target yang diprediksi "tidak ada pemetaan" / jumlah butir tanpa target.
- Butir AMBIGUOUS (16) dan COMPOSITE (3) dikeluarkan dari skor inti dan dilaporkan terpisah.

Klasifikasi foto. Unit = satu foto (gold: `data_evaluasi/gambar/manifest/gold_gambar_manifest_final.csv`, kolom `label_kind`; 158 foto setelah 2 dikeluarkan; versi awal 160: `gold_gambar_manifest.csv`).

- **Macro-F1** = rata-rata F1 tiga kelas KNOWN, OTHER, UNCERTAIN (kelas sama berat).
- **Top-1 pada KNOWN** = foto KNOWN dengan status KNOWN dan varietas benar / jumlah foto KNOWN.
- Ambang keyakinan dipilih pada split `val` (51 foto pada gold final); skor dilaporkan pada split `test` (107 foto).

## 4. Ukuran F2 (mode adaptif; eksploratori)

Dihitung oleh `data_evaluasi/skrip/analisis_kanonik_dinamis.py` dari keluaran harness (`mapping.csv` dengan kolom `acquisition_status`, `trace.json`, `rows_final.json`).

| Kode | Ukuran | Definisi |
|---|---|---|
| F2-1 | Akuisisi | per dataset: kandidat dinilai (atribut tanpa padanan yang lolos penjaga), baris baru (`NEW_ROW`), duplikat dari baris yang ada (`DUPLICATE_OF`), bukan karakter (`NOT_CHARACTERISTIC`), gagal (`FAILED`); jumlah baris Excel |
| F2-2 | Penggunaan ulang | atribut yang dipetakan ke baris akuisisi dari dataset sebelumnya (tanpa akuisisi baru), dibagi jumlah atribut tanpa padanan template pada dataset itu |
| F2-3 | Anti duplikat | jumlah baris akuisisi dibanding jumlah kandidat; jumlah pasangan label dengan kemiripan tinggi (rasio >= 0,78) yang ditinjau kurator sebagai duplikat atau bukan |
| F2-4 | Keamanan | Mapping F1 terhadap gold dengan prediksi baris akuisisi diabaikan (hanya template), dan versi ketat (baris akuisisi dihitung salah positif pada butir NO_MATCH); selisih terhadap mode beku pada dataset yang sama |
| F2-5 | Stabilitas | jumlah baris akuisisi per pengulangan dan kemiripan himpunan label antar pengulangan (Jaccard); tiga pengulangan dari database kosong |
| F2-6 | Kualitas baris | proporsi baris akuisisi yang merupakan karakter tanaman yang sah (tinjauan kurator; sementara tinjauan model sampai diverifikasi peneliti) |

Ukuran F2 tidak masuk koreksi Holm. Hasilnya dibaca bersama keterbatasan: satu urutan dataset, satu domain, penilai akuisisi berbasis model bahasa.

## 5. Varian pembanding (mode beku)

| Komponen | Varian | Sumber prediksi |
|---|---|---|
| Atribut | S4 sistem penuh | *Proposed canonical key* |
| Atribut | S1 exact-name saja | kunci yang sama hanya bila *Mapping method* = exact_name |
| Atribut | S2 retrieval top-1 tanpa LLM | `retrieval_s2_key` (hanya dari harness L1; UI tidak menampilkannya) |
| Atribut | S3 LLM saja tanpa retrieval | aproksimasi (seluruh 60 baris ke penilai) lewat `--s3`; sudah dijalankan, lihat HASIL_SEMENTARA bagian 12 |
| Foto | V3 fusi tiga sinyal | tindakan fusi dari *classification_status* dan *write_reason* (review dihitung sebagai status visual) |
| Foto | V3b | sama dengan V3, tetapi tindakan review dihitung UNCERTAIN (analisis sensitivitas) |
| Foto | V1 hanya gambar | status VLM mentah |
| Foto | V2 hanya nama file | dihitung luring dari nama berkas |

## 6. Aturan pelaporan

1. Kelompok data **R** (riset nyata: R01, R02), **N** (sumber publik: N07, N08, N09), dan **S** (sintetis: S01 sampai S04) dilaporkan terpisah. S hampir seluruhnya mudah dan tidak boleh dicampur.
2. Beri confidence interval bootstrap 95% pada tiap metrik karena jumlah butir kecil (326 atribut, 158 foto pada gold final). Perbandingan antar varian memakai
   paired bootstrap (10.000 ulangan) dengan koreksi Holm pada perbandingan confirmatory (S4 vs S1, S4 vs S2, V3 vs V1, V3 vs V2 pada nama file MENYESATKAN);
   lainnya eksploratori. Laporkan ukuran efek dan variasi antar 3 pengulangan; selisih lebih kecil dari variasi itu tidak diklaim. Catatan: model tidak deterministik; skor agregat identik antar pengulangan pada dataset yang diuji, tetapi satu atau dua butir bergeser.
3. Gold atribut final diverifikasi langsung oleh penulis butir per butir (`terverifikasi_v1`); belum ada dua anotator independen
   (template di `data_evaluasi/anotasi_buta/`). Konsistensi diukur dengan anotasi ulang buta 100 butir (kappa 0,97).
3a. Laporkan **held-out (R02, N07, N08, N09)** terpisah dari **dev (R01, S01 sampai S04)**, dan per stratum: butir yang dapat diselesaikan lookup
   (label kanonik persis atau alias terdaftar) vs butir yang memerlukan semantik. Alias `row_aliases.yaml` dibekukan.
4. Kelas foto kecil (Paprika, Serrano, Padron, Poblano, Shishito) tidak dilaporkan per kelas.
5. Gold foto Commons berasal dari label komunitas Commons yang diverifikasi penulis; bukan verifikasi ahli botani. Foto Commons adalah **proksi luar negeri**.
6. 21 dari 60 kunci kanonik tidak pernah menjadi target gold, jadi recall per kunci tidak dilaporkan.
7. S04 dan N08 (berkas asli) ditolak sistem; dilaporkan sebagai kasus penolakan, bukan skor. N08 dievaluasi dari berkas varian (deviasi D4).

## 7. Rujukan (dari pencarian literatur; periksa ulang bagian metriknya sebelum mengutip)

- Towards Scalable Schema Mapping using Large Language Models. https://arxiv.org/pdf/2505.24716 (Precision, Recall, F1).
- Schema Matching with Large Language Models: an Experimental Study. https://arxiv.org/pdf/2407.11852.
- ReMatch: Retrieval Enhanced Schema Matching with LLMs. https://arxiv.org/html/2403.01567v2.
- Column Type Annotation using ChatGPT. https://arxiv.org/pdf/2306.00745 (micro-F1).
- A Survey on Open-Set Image Recognition. https://arxiv.org/pdf/2312.15571 (macro-F1 dan metrik open-set).
- Benchmark open-set penyakit tanaman (CNN, ViT, VLM), Frontiers in Plant Science 2025. https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2025.1623907/epub.
