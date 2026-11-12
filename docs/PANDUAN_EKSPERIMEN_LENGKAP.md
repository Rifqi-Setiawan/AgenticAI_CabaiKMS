# Panduan Lengkap Eksperimen CABAI-KMS

Diperbarui **12 November 2026** (visi dua tahap D24). Hasil terbaru (data level varietas D19, embedding bge-m3 D22, deskripsi
varietas untuk model visi D20, nama file berpasangan D23, model visi buta nama berkas D24) ada di **Bagian 1** dan
**Bagian 6A**. Bagian 3-6 lainnya masih
menjelaskan data dan hasil **paper draf v11 (4 November 2026)**, sebelum pembersihan level varietas; definisi metrik di
Bagian 5 tetap berlaku. Ringkasan yang mudah dibaca: `docs/SKOR METRIKS EVALUASI.md`.
Dokumen ini menggantikan `docs/HASIL_SEMENTARA_EKSPERIMEN.md` dan `data_evaluasi/STATUS_PROGRES.md` (versi 1 November, usang).

Daftar isi:
1. Ringkasan satu halaman (hasil terbaru)
2. Apa yang diuji
3. Data yang dipakai (paper v11)
4. Kunci jawaban (gold)
5. Metrik dan cara menghitungnya
6A. Hasil terbaru (atribut 7-8 Nov, foto 12 Nov 2026)
6. Hasil paper v11 (4 November 2026)
7. Status pekerjaan
8. Peta berkas

---

## 1. Ringkasan satu halaman

### Hasil terbaru (atribut 7-8 November, foto 12 November 2026)

| Bagian | Data | Hasil utama |
|---|---|---|
| Retrieval (tanpa LLM) | 109 butir semantik gold terverifikasi | bge-m3 Hit@1 0,826, Hit@8 **1,000**, **MRR 0,883** (MiniLM 0,376 / 0,789 / 0,517) |
| Pemetaan atribut | R02, N07, N08, N09 held-out (71 / 137); S01-S03 dev (70 / 7); 3 rep | F1 S4 held-out **1,000** (MiniLM 0,978), dev **1,000** (MiniLM 0,915); S1 0,621, S2 0,420 |
| Tulis otomatis | 285 butir | 141 ditulis otomatis, **0 salah**; 139 (49%) ke review, semuanya usulan NULL |
| Isi spreadsheet per sel (ketat) | 328 sel kunci | held-out 216/216, dev 112/112 = **1,000** |
| Foto Commons (D24) | 35 foto, registri Hungarian Wax | 32/35 status benar, AUTO_LINK 5/6 (D23: 35/35, 7/7) |
| Foto Indonesia (D24) | 6 foto x S01-S03 | Top-1 0,750, AUTO_LINK **12/13**, bagian **18/18** (D23: 0,812, 12/12, 15/18) |
| Foto PVT (D24) | 40 foto, registri + deskripsi 24 varietas P01 | Top-1 kartu terlihat 0,579, kartu tertutup **0,158**; AUTO_LINK 8/13 dan **2/6** (D23: 0,632 / 0,211; 12/19 / 3/8) |
| Nama file berpasangan (D24) | 40 PVT kartu tertutup x 3 nama | nama salah terdaftar: REVIEW_MISMATCH **7/40** (D23 0/40), ikut nama berkas **2/40** (D23 30/40); tautan salah semua kondisi **8/120** (D23 17/120) |
| Workbook gabungan (D24) | Indonesia S01-S03 | F1 **0,980** (sel 1,000; link foto 12 benar / 1 salah / 4 terlewat; D23 0,960) |

Kesimpulan singkat: pemetaan atribut sempurna pada data level varietas dan tidak pernah menulis salah. Sejak D24 model visi
tidak lagi bisa disetir nama berkas, dan tautan foto yang salah berkurang separuh. Kemampuan mengenali varietas Indonesia
yang mirip dari tampilan saja tetap rendah (PVT kartu tertutup 4/19 foto KNOWN dengan nama netral, sama di D23 dan D24).

### Hasil paper v11 (4 November 2026, data dan sistem lama)

| Bagian | Data | Hasil utama (sistem penuh S4 / V3) |
|---|---|---|
| Pemetaan atribut | 9 workbook, 299 atribut dinilai (held-out 208) | F1 held-out **0,978** [0,929; 1,000], presisi 1,000, recall NULL 1,000 |
| Pembanding atribut | S1 nama persis, S2 retrieval top-1, S2+τ | F1 held-out 0,621 / 0,377 / 0,460; S4 lebih tinggi di **8 dari 8 workbook** |
| Isi spreadsheet per sel | 600 sel kunci | held-out (posisi) presisi 1,000, recall 0,898, F1 0,946; ketat 0,591 karena bug kolom varietas N07/R02 (setelah diperbaiki 1,000) |
| Tulis otomatis | 293 atribut berkeluaran | 129 ditulis otomatis, **128 benar** (0,992); 164 (56%) ke review, semuanya usulan NULL |
| Foto Commons | 160 foto (terkoreksi D18) | macro-F1 **0,640**, Top-1 0,727, presisi AUTO_LINK 0,736 (nama netral **0,644**) |
| Foto Indonesia | 12 foto x 3 spreadsheet (gold peneliti) | macro-F1 (KNOWN/OTHER) 0,706, Top-1 0,773, AUTO_LINK 15/24 = 0,625 |
| Foto gabungan | 196 keputusan | macro-F1 0,632, Top-1 0,736, AUTO_LINK **79/111 = 0,712** |
| Workbook gabungan | sel atribut + link foto | F1 semua run **0,820** (Indonesia 0,872; Commons, hanya foto, 0,677) |

Kesimpulan singkat: pemetaan atribut sangat akurat dan hampir tidak pernah menulis salah (kesalahannya berupa *tidak menulis*
lalu dikirim ke review). Tautan foto cukup baik bila nama file informatif, tetapi masih menautkan varietas yang mirip atau foto
yang tak jelas dengan keyakinan tinggi.

---

## 2. Apa yang diuji

### 2.1 Sistem
CABAI-KMS mengubah spreadsheet karakterisasi cabai (format apa pun) menjadi **template kanonik 60 baris** (55 karakter morfologi
dalam domain vegetatif, daun, bunga, buah, biji; 1 baris Lokasi; 4 baris Gambar Daun/Batang/Buah/Bunga), lalu menautkan foto
dari folder Google Drive ke kolom varietas yang benar.

Alur atribut: parser -> kolom varietas (anchor) -> **nama persis** (label/alias) -> bila tidak cocok: **retrieval embedding**
(kandidat baris) -> **LLM reranker** (pilih baris atau NULL) -> **verifier** deterministik -> **gerbang penerimaan**
(AUTO_ACCEPT ditulis; REVIEW tidak ditulis) -> normalisasi nilai -> workbook kanonik.

Alur foto: daftar varietas = kolom varietas workbook kanonik (+ varietas di database KMS) -> **model visi** menerima foto,
nama file, dan daftar varietas -> status KNOWN / OTHER / UNCERTAIN + varietas + bagian tanaman + keyakinan -> **aturan fusi**:
- AUTO_LINK: status KNOWN, keyakinan >= 0,85, varietas terdaftar, nama file tidak bertentangan -> link foto ditulis.
- CANDIDATE: status OTHER, keyakinan >= 0,80 -> antrean varietas baru.
- REVIEW: selebihnya (bertentangan, ragu, UNCERTAIN).

Catatan penting: model visi **hanya menerima nama** varietas dari spreadsheet; deskripsi morfologi hanya untuk varietas di
kolom referensi template (Gendot, Kopay, Katokkon, Cabai rawit NTB, dst.).

Model: teks `ag/gemini-3.8-flash-medium`, visi `ag/gemini-3.8-flash-high` (lewat gateway 9Router), embedding
`paraphrase-multilingual-MiniLM-L12-v2` (run sebelum D22; sejak 5 Nov 2026 sistem memakai `BAAI/bge-m3`).

### 2.2 Varian pembanding
| Varian | Isi |
|---|---|
| **S1** | hanya pencocokan nama persis |
| **S2** | ambil kandidat retrieval peringkat 1 untuk semua atribut, tidak pernah menolak |
| **S2+τ** | seperti S2, tetapi menolak (NULL) bila jarak kosinus > τ = 0,386 (dituning di dev, dibekukan) |
| **S3** | sistem penuh tanpa retrieval: reranker melihat seluruh 60 baris |
| **S4** | sistem penuh |
| **V2** | foto: hanya nama file |
| **V1 / V3** | foto: hanya visual / fusi visual + nama file + daftar varietas (statusnya identik; fusi mengubah apa yang *ditulis*) |

---

## 3. Data yang dipakai

Semua salinan input dan keluaran sistem ada di `dataset_eksperimen/` (rinci: `KETERANGAN_DATA.txt`,
`DESKRIPSI_PEMBUATAN_DAN_TUJUAN_DATA.txt`, checksum `SHA256SUMS.txt`).

### 3.1 Workbook atribut (dinilai)
| ID | Berkas | Sumber | Bentuk | Split | Atribut | Target / NULL |
|---|---|---|---|---|---|---|
| R01 | data_input.xlsx | data lapangan asli peneliti | baris, header 2 tingkat | dev | 14 | 1 / 13 |
| S01 | D01_transposed_indonesia_mixed.xlsx | sintetis | transposed | dev | 21 | 20 / 1 |
| S02 | D02_row_flat_english_semantic.xlsx | sintetis | baris, Inggris | dev | 26 | 22 / 4 |
| S03 | D03_row_multilevel_indonesia.xlsx | sintetis | baris, header 2 tingkat | dev | 30 | 28 / 2 |
| R02 | input_cabai_kms.xlsx | gabungan Zenodo + Kementan | baris, campuran | held-out | 54 | 18 / 32 |
| N07 | E07_kementan_deskripsi_ext.xlsx | 3 SK varietas Kementan | baris | held-out | 70 | 20 / 45 |
| N08 | E08_zenodo_capsicum_en_variety.xlsx | Zenodo (Brasil) | baris, Inggris | held-out | 23 | 9 / 12 |
| N09 | dataset_cabai_deskripsi_varietas.xlsx | 6 deskripsi varietas resmi | transposed | held-out | 80 | 24 / 48 |
| S04 | D04_varietas_kosong_invalid.xlsx | sintetis, sengaja tidak valid | baris | - | 8 | uji penolakan |

Total 326 atribut; **299 dinilai** (142 bertarget, 157 NULL). S04 dan berkas N08 asli diuji penolakan. 19 atribut
AMBIGUOUS/COMPOSITE dikeluarkan dari skor inti (dianalisis terpisah, bagian 6.3).

### 3.2 Foto
| Set | Jumlah | Asal label | Dipakai |
|---|---|---|---|
| **Commons** (`2_input_foto/commons_8_folder`, F1-F8) | 160 (KNOWN 99, OTHER 45, UNCERTAIN 16) | kategori Wikimedia Commons | metrik foto utama |
| **Indonesia** (`2_input_foto/foto_indonesia_drive1`) | 12 (10 dinilai per run) | nama berkas peneliti | dijalankan bersama S01, S02, S03 |
| Berita Resmi PVT (pilot) | 317 (40 diuji) | dokumen resmi Kementan | **tidak dipakai** (125 px, kartu nama varietas = bocoran label) |

Nama file Commons dibuat dalam tiga kondisi: INFORMATIF 64 (mis. `jalapeno_buah_117.jpg`), NETRAL 64 (`IMG_0061.jpg`),
MENYESATKAN 32 (menyebut varietas terdaftar yang salah).

### 3.3 Spreadsheet pendamping foto
- Run paper: `spreadsheet_varietas_terdaftar.xlsx` (sintetis, 8 nama: Cabai Rawit, Jalapeno, Habanero, Cayenne, Paprika,
  Cabai Korea, Serrano, Hungarian Wax).
- Pengganti data asli (4 Nov, belum ada hasil): `G01_grin_8_varietas_terdaftar.xlsx` dan `G02_grin_11_varietas.xlsx`
  dari bank genetik USDA GRIN (bagian 7).

### 3.4 Template
`3_template_kanonik/template_kanonik.xlsx`: 60 baris, 10 varietas referensi. Kunci baris stabil di `src/schema/row_keys.yaml`.

---

## 4. Kunci jawaban (gold)

| Gold | Berkas | Cara dibuat | Catatan |
|---|---|---|---|
| Pemetaan atribut | `data_evaluasi/gold/final/gold_semua_dataset_final.csv` | diverifikasi butir per butir oleh penulis | status ONE_TO_ONE / NO_MATCH / AMBIGUOUS / COMPOSITE |
| Konsistensi gold | `data_evaluasi/anotasi_buta/subset_v1/hasil/laporan_kappa.md` | 100 butir dianotasi ulang buta oleh peneliti yang sama | kesepakatan 0,98; kappa 0,97 (target), 0,96 (dipetakan vs NULL) |
| Isi sel | `data_evaluasi/gold/kunci_sel/kunci_sel_semua.csv` | otomatis dari gold pemetaan + nilai mentah sumber (pembaca terpisah dari parser sistem) | 600 sel |
| Foto Commons | `data_evaluasi/gambar/manifest/gold_gambar_manifest.csv` | kategori Commons | versi kedua (tinjauan visual) untuk uji sensitivitas |
| Foto Indonesia | `data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv` | diisi peneliti 4 Nov (varietas, bagian, layak); status per spreadsheet diturunkan otomatis (`skrip/buat_gold_foto_indonesia.py`) | 3 varietas kosong diisi dari tinjauan visual dan disetujui penulis; gold lama `gold_kombinasi_drive1.csv` tidak dipakai lagi |

Keterbatasan: gold atribut bukan buatan pakar independen; kappa mengukur konsistensi peneliti sendiri, bukan validitas.

---

## 5. Metrik dan cara menghitungnya

Kode inti: `data_evaluasi/skrip/hitung_metrik.py` (fungsi `attr_metrics`, `img_metrics`, `bootstrap`, `ci`).

### 5.1 Pemetaan atribut
Hanya atribut ONE_TO_ONE (bertarget) dan NO_MATCH (NULL) yang dinilai.

- **Precision** = (prediksi baris yang benar) / (semua prediksi yang tidak NULL)
- **Recall** = (prediksi baris yang benar) / (semua atribut bertarget)
- **F1** = 2 x P x R / (P + R)
- **Recall NULL** = (atribut NO_MATCH yang dibiarkan NULL) / (semua atribut NO_MATCH)

Contoh, S4 held-out: 71 atribut bertarget, sistem memprediksi baris untuk 68 atribut dan semuanya benar.
P = 68/68 = 1,000; R = 68/71 = 0,958; F1 = 2 x 1 x 0,958 / 1,958 = **0,978**. Ke-137 atribut NULL semuanya dibiarkan NULL,
jadi recall NULL = 137/137 = 1,000.

### 5.2 Isi spreadsheet per sel
Definisi lengkap di docstring `data_evaluasi/skrip/akurasi_sel.py`.
- Sel harapan (baris, varietas) = nilai mentah semua atribut sumber yang gold-nya ONE_TO_ONE ke baris itu.
- Sel benar = terisi, di kolom varietas yang benar, dan himpunan nilainya sama setelah penyeragaman ringan (huruf kecil, koma
  desimal -> titik, tanda rentang -> "--", spasi). Baris Gambar tidak dinilai.
- **Ketat**: kolom dicocokkan lewat nama varietas di header. **Posisi**: kolom ke-i dianggap varietas ke-i sumber.
- Precision = sel benar / sel terisi; Recall = sel benar / sel harapan.
- **Normalisasi**: setiap sel yang teksnya berubah dari sumber dicek apakah maknanya tetap.

### 5.3 Foto
- **Macro-F1 status**: F1 dihitung terpisah untuk kelas KNOWN, OTHER, UNCERTAIN (status saja), lalu dirata-rata.
- **Top-1 pada foto KNOWN**: foto gold KNOWN yang statusnya KNOWN **dan** varietasnya benar / semua foto gold KNOWN.
- **Presisi AUTO_LINK**: tautan otomatis yang benar (gold KNOWN dan varietas sama) / semua tautan otomatis.

Contoh macro-F1, 160 foto Commons (baris = gold, kolom = sistem):

| gold \ sistem | KNOWN | OTHER | UNCERTAIN | total |
|---|---|---|---|---|
| KNOWN | 81 | 15 | 3 | 99 |
| OTHER | 15 | 30 | 0 | 45 |
| UNCERTAIN | 4 | 6 | 6 | 16 |

KNOWN: P = 81/100 = 0,810, R = 81/99 = 0,818, F1 = 0,814. OTHER: P = 30/51 = 0,588, R = 30/45 = 0,667, F1 = 0,625.
UNCERTAIN: P = 6/9 = 0,667, R = 6/16 = 0,375, F1 = 0,480. Macro-F1 = (0,814 + 0,625 + 0,480) / 3 = **0,640**.

Contoh presisi AUTO_LINK nama netral: dari 64 foto bernama `IMG_xxxx`, 45 ditautkan otomatis, 29 benar -> 29/45 = **0,644**
(rincian per foto dengan gambar: `data_evaluasi/hasil_eksperimen/rincian_autolink_netral.xlsx`).

### 5.4 Statistik
- **Selang kepercayaan (CI) 95% atribut**: bootstrap **per workbook** (10.000 resampel), karena atribut dari satu workbook
  saling berkaitan. Perbedaan antarvarian memakai bootstrap berpasangan per workbook dengan koreksi Holm, ditambah uji tanda
  per workbook.
- **CI foto**: bootstrap per foto (10.000 resampel).

---

## 6A. Hasil terbaru (atribut 7-8 Nov, foto 12 Nov 2026)

Semua run: data level varietas (D19), bge-m3 (D22), `KMS_DYNAMIC_SCHEMA=0`, tanpa Commit ke KMS (jumlah baris tabel kms.*
sama sebelum dan sesudah run atribut). Atribut lewat harness `harness_vps.py` yang memanggil `run_pipeline_ui()`; foto lewat
`uji_visi_commons_vps.py` (langkah `vision_hook` dengan modul produksi, deskripsi varietas D20, tanpa Drive dan tanpa tulis
KMS). Model teks `ag/gemini-3.8-flash-medium`, visi `ag/gemini-3.8-flash-high`. Uji paritas jalur produksi penuh belum
dijalankan.

### 6A.1 Retrieval (`banding_embedding.py`, tanpa LLM)
Butir semantik ONE_TO_ONE (tidak selesai lewat exact-name). Gold terverifikasi n = 109; gold PVT belum diverifikasi n = 96.

| Model | Hit@1 | Hit@3 | Hit@5 | Hit@8 | MRR | PVT Hit@1 / Hit@8 / MRR |
|---|---|---|---|---|---|---|
| paraphrase-multilingual-MiniLM-L12-v2 | 0,376 | 0,578 | 0,670 | 0,789 | 0,517 | 0,344 / 0,771 / 0,486 |
| paraphrase-multilingual-mpnet-base-v2 | 0,468 | 0,716 | 0,853 | 0,908 | 0,622 | 0,427 / 0,750 / 0,540 |
| BM25 | 0,578 | 0,752 | 0,807 | 0,872 | 0,682 | 0,635 / 0,927 / 0,733 |
| harrier-oss-v1-270m | 0,642 | 0,826 | 0,844 | 0,908 | 0,742 | 0,604 / 0,823 / 0,680 |
| multilingual-e5-base | 0,743 | 0,872 | 0,917 | 0,945 | 0,816 | 0,698 / 0,875 / 0,752 |
| Qwen3-Embedding-0.6B | 0,752 | 0,872 | 0,917 | 0,963 | 0,825 | 0,677 / 0,833 / 0,730 |
| harrier-oss-v1-0.6b | 0,752 | 0,881 | 0,927 | 0,945 | 0,826 | 0,594 / 0,823 / 0,681 |
| **BAAI/bge-m3** | **0,826** | **0,927** | **0,972** | **1,000** | **0,883** | 0,688 / 0,927 / 0,771 |
| bge-m3 + BM25 (RRF) | 0,697 | 0,844 | 0,881 | 0,917 | 0,782 | 0,646 / 0,969 / 0,755 |

Selisih Hit@1 bge-m3 - MiniLM +0,450 (CI 95% +0,358 sampai +0,541). Varian instruksi Qwen3 dan RRF lain di `ringkasan.csv`.
Hasil: `hasil_eksperimen/hasil_retrieval/banding_embedding/` dan `banding_embedding_putaran1/`.

### 6A.2 Pemetaan atribut end-to-end (`skor_atribut_e2e.py`, 3 pengulangan)

| Himpunan | Varian | n target / NULL | Precision | Recall | F1 (CI 95%) | Recall NULL |
|---|---|---|---|---|---|---|
| held-out | S1 | 71 / 137 | 1,000 | 0,451 | 0,621 (0,484-0,720) | 1,000 |
| held-out | S2 | 71 / 137 | 0,283 | 0,817 | 0,420 (0,345-0,495) | 0,022 |
| held-out | **S4** | 71 / 137 | **1,000** | **1,000** | **1,000** (1,000-1,000) | **1,000** |
| dev S01-S03 | S1 | 70 / 7 | 1,000 | 0,086 | 0,158 | 1,000 |
| dev S01-S03 | S2 | 70 / 7 | 0,800 | 0,857 | 0,828 | 0,286 |
| dev S01-S03 | **S4** | 70 / 7 | **1,000** | **1,000** | **1,000** | **1,000** |

Per workbook F1 S4 (bge-m3 / MiniLM): R02 1,000 / 1,000; N07 1,000 / 0,974; N08 1,000 / 0,875; N09 1,000 / 1,000;
S01 1,000 / 0,974; S02 1,000 / 1,000; S03 1,000 / 0,783. Uji berpasangan S4 (rep1): held-out +0,022 (CI +0,000 sampai
+0,050, p 0,095); input identik R02/N07/N09 +0,008 (+0,000 sampai +0,027, p 0,735); dev +0,085 (+0,038 sampai +0,140,
p < 0,001). 14 butir berubah dari NULL ke benar, 0 memburuk. AUTO_ACCEPT benar held-out 71 (MiniLM 68), dev 70 (59); salah 0.
Keputusan identik di tiga pengulangan. Latensi praktis sama (R02 330 s, N07 418 s, N09 534 s).
Hasil: `hasil_eksperimen/skor_atribut_e2e_bge-m3/`, run `hasil_harness/2026-11-07_bge-m3/`.

### 6A.3 Isi spreadsheet per sel (mode ketat, `akurasi_sel.py`)
Kolom varietas benar di semua workbook. Sel benar / harapan: R02 79/79, N07 37/37, N08 27/27, N09 73/73, S01 40/40,
S02 44/44, S03 28/28 (salah tulis 0, terlewat 0). Normalisasi: 83 dari 328 sel berubah tetapi setara, 0 berbeda makna.

### 6A.4 Foto (`skor_foto_ulang.py`)

| Set | Foto | Status benar | Macro-F1 kelas gold | Top-1 KNOWN | Recall OTHER | AUTO_LINK benar | Bagian benar |
|---|---|---|---|---|---|---|---|
| Commons, registri Hungarian Wax | 35 | 35/35 | 1,000 | 7/7 | 28/28 | 7/7 | 31/32 |
| Indonesia S01-S03 | 18 | 15/18 | 0,734 | 13/16 | 2/2 | 12/12 | 15/18 |
| PVT kartu terlihat, registri P01 | 40 | 27/40 | 0,864 | 12/19 | 15/21 | 12/19 | 36/36* |
| PVT kartu tertutup, registri P01 | 40 | 4/40 | 0,276 | 4/19 | 0/21 | 3/8 | 35/36* |

\*Gold bagian PVT diverifikasi penulis. Satu foto S02 gagal provider (InstructorRetryException) dan dijalankan ulang (percobaan 2).
Hasil: `hasil_eksperimen/foto_ulang_2026-11-07/`.

### 6A.5 Nama file berpasangan (D23, `skor_nama_file_berpasangan.py`)
40 foto PVT kartu tertutup, registri 24 varietas P01; tindakan sesuai gold / status benar / AUTO_LINK salah / ikut nama berkas:

| Foto | Nama netral | Nama benar | Nama salah terdaftar |
|---|---|---|---|
| KNOWN (19) | 16/19, 4/19, 3, - | 12/19, 16/19, 0, - | **0/19**, 1/19, **7**, 16/19 |
| OTHER (21) | 3/21, 0/21, 2, - | 17/21, 19/21, 0, - | **0/21**, 0/21, **5**, 14/21 |

Uji berpasangan (proporsi tindakan sesuai gold): KNOWN salah vs netral -0,842 (CI -1,000 sampai -0,684); OTHER benar vs
netral +0,667 (+0,381 sampai +0,905). Indonesia nama netral vs asli: KNOWN 11/16 vs 12/16. Nama berkas masuk ke prompt
model visi, sehingga pemeriksaan silang nama vs visual tidak independen (keputusan perbaikan belum diambil, D23).
Hasil: `hasil_eksperimen/foto_nama_berpasangan_2026-11-07/`.

### 6A.6 Workbook gabungan
Indonesia S01-S03: sel 112/112 benar; link foto 9 benar, 3 salah, 7 terlewat; gabungan P 0,976, R 0,945, **F1 0,960**.
P01 + PVT (gold atribut P01 belum diverifikasi): kartu terlihat F1 0,950, kartu tertutup 0,940.
(Angka 6A.4-6A.6 adalah run D23, 7 Nov. Hasil foto terbaru D24 ada di 6A.7.)

### 6A.7 Visi dua tahap (D24, 12 Nov 2026; `job_m2.sh`, `ablasi_fusi_m2.py`)
Model visi tidak menerima nama berkas/caption; nama berkas dicocokkan deterministik ke registri, lalu digabung di
`fuse_photo_signals(independent_signals=True)`. Semua 271 panggilan visi D23 diulang dengan input, registri, deskripsi,
kanonik P01/S01-S03, dan varietas DB yang sama (`--db-dari-meta`); 0 gagal. Skrip skor sama (direproduksi byte-identik pada
data 7 Nov). Ablasi: jawaban visual D24 digabung ulang dengan aturan fusi lama, tanpa memanggil model.

| Metrik | D23 | D24, fusi lama (ablasi) | **D24** |
|---|---|---|---|
| PVT nama salah terdaftar: ikut nama berkas | 30/40 | 2/40 | **2/40** |
| PVT nama salah terdaftar: REVIEW_MISMATCH | 0/40 | 3/40 | **7/40** |
| PVT berpasangan: tindakan sesuai gold | 48/120 | 29/120 | **33/120** |
| PVT berpasangan: AUTO_LINK salah | 17/120 | 12/120 | **8/120** |
| PVT KNOWN nama netral: status benar / tindakan benar | 4/19, 16/19 | 4/19, 16/19 | **4/19, 16/19** |
| PVT KNOWN nama benar: status benar / tindakan benar | 16/19, 12/19 | 3/19, 4/19 | **3/19, 4/19** |
| PVT OTHER nama benar (tidak terdaftar): tindakan benar | 17/21 | 3/21 | **3/21** |
| Commons: status benar / AUTO_LINK benar | 35/35, 7/7 | sama dengan D24 | **32/35, 5/6** |
| Indonesia S01-S03: Top-1 / AUTO_LINK benar / bagian | 0,812, 12/12, 15/18 | sama dengan D24 | **0,750, 12/13, 18/18** |
| PVT kartu terlihat / tertutup: Top-1 | 0,632 / 0,211 | sama dengan D24 | **0,579 / 0,158** |
| Workbook gabungan Indonesia F1 | 0,960 | sama dengan D24 | **0,980** |

Kebocoran nama berkas hilang; kondisi netral identik, jadi turunnya total tindakan benar berasal dari skor D23 kondisi "nama
benar" yang terlalu tinggi. Aturan fusi baru hanya mengubah 8 dari 271 tindakan (semua di set PVT berpasangan). Satu ulangan;
selisih kecil di set foto ulang ada di dalam CI. Hasil: `hasil_eksperimen/foto_two_stage_2026-11-12/` (`LAPORAN_M2.md`).

---

## 6. Hasil paper v11 (4 November 2026)

### 6.1 Pemetaan atribut per varian
| Varian | Held-out P | R | F1 [CI per workbook] | Recall NULL | Semantik held-out F1 | Dev F1 |
|---|---|---|---|---|---|---|
| S1 nama persis | 1,000 | 0,451 | 0,621 [0,500; 0,688] | 1,000 | 0,000 | 0,156 |
| S2 retrieval top-1 | 0,254 | 0,732 | 0,377 [0,299; 0,411] | 0,022 | 0,189 | 0,352 |
| S2+τ | 0,345 | 0,690 | 0,460 [0,335; 0,518] | 0,438 | 0,228 | 0,372 |
| S3 tanpa retrieval | 1,000 | 1,000 | 1,000 | 1,000 | 1,000 | - |
| **S4 sistem penuh** | 1,000 | 0,958 | **0,978 [0,929; 1,000]** | 1,000 | 0,960 | 0,909 |

Selisih held-out (CI per workbook): S4-S1 +0,357 [0,291; 0,438]; S4-S2 +0,602 [0,576; 0,633]; S4-S2+τ +0,518 [0,462; 0,600].
S4 lebih tinggi dari ketiga pembanding di 8 dari 8 workbook (uji tanda satu sisi p = 0,004; held-out saja p = 0,063).
S4 vs S3: -0,022 [-0,071; 0,000], tidak signifikan.

### 6.2 F1 per workbook
| Varian | R01 | S01 | S02 | S03 | R02 | N07 | N08 | N09 |
|---|---|---|---|---|---|---|---|---|
| S1 | 0,000 | 0,333 | 0,000 | 0,133 | 0,615 | 0,710 | 0,364 | 0,629 |
| S2 | 0,143 | 0,537 | 0,383 | 0,246 | 0,418 | 0,405 | 0,207 | 0,375 |
| S2+τ | 0,222 | 0,500 | 0,450 | 0,250 | 0,491 | 0,542 | 0,222 | 0,459 |
| S3 | 0,667 | - | - | - | 1,000 | 1,000 | 1,000 | 1,000 |
| S4 | 0,667 | 0,974 | 1,000 | 0,783 | 1,000 | 0,974 | 0,875 | 1,000 |

R01 hanya punya 1 atribut bertarget, jadi F1-nya kasar.

### 6.3 Sensitivitas 19 atribut AMBIGUOUS/COMPOSITE (held-out)
Contoh: "Panjang buah" (tahap buah tidak disebut), "Ukuran daun" (panjang dan lebar dalam satu sel). S4 memilih NULL untuk 17.

| Aturan | S1 | S2 | S2+τ | S4 |
|---|---|---|---|---|
| Inti (dikeluarkan) | 0,621 | 0,377 | 0,460 | 0,978 |
| Longgar (kunci mana pun benar, NULL = salah) | 0,525 | 0,389 | 0,463 | 0,875 |
| Pesimis (tidak pernah benar) | 0,525 | 0,331 | 0,398 | 0,850 |
| Abstain dianggap benar | 0,621 | 0,364 | 0,447 | 0,978 |

S4 tetap unggul minimal 0,32 dari setiap pembanding pada semua aturan.

### 6.4 Retrieval
Pada 104 atribut semantik bertarget: baris benar ada di kandidat peringkat 1 untuk 40,4%, di 8 teratas 77,9%, di seluruh
kandidat 86,5% (MRR 0,534). Ke-14 kesalahan semantik S4 semuanya karena baris benar **tidak terambil** retrieval, dan di semua
kasus reranker menjawab NULL (tidak pernah memilih baris salah). Latency: S4 1.573 detik vs S3 1.511 detik (lima workbook).

### 6.5 Penulisan otomatis dan beban review
Dari 293 atribut berkeluaran: 129 ditulis otomatis (128 benar, presisi 0,992; satu salah: kolom "No" R01 dipetakan ke Lokasi).
164 (56%) ke review, **semuanya usulan NULL** (tidak ada baris yang ditahan karena keyakinan rendah). Dari 164 itu, 150 memang
NO_MATCH (kebanyakan atribut agronomi/administrasi: umur panen, hasil, pemulia) dan 14 target yang terlewat. Ke-164 butir hanya
punya 106 label unik.

### 6.6 Isi spreadsheet per sel (keluaran paper)
| Workbook | Kolom varietas benar | Ketat F1 | Posisi P / R / F1 |
|---|---|---|---|
| R01 | 2/2 | 0,000 | 0,000 / 0,000 / 0,000 (sel Lokasi tercampur kolom "No") |
| R02 | **0/6** | **0,000** | 1,000 / 1,000 / 1,000 |
| N07 | **0/3** | **0,000** | 1,000 / 0,973 / 0,986 |
| N08 | 17/17 | 0,875 | 1,000 / 0,778 / 0,875 |
| N09 | 6/6 | 1,000 | 1,000 / 1,000 / 1,000 |
| S01 | 4/4 | 0,974 | 1,000 / 0,949 / 0,974 |
| S02 | 3/3 | 1,000 | 1,000 / 1,000 / 1,000 |
| S03 | 4/4 | 0,783 | 1,000 / 0,643 / 0,783 |

Gabungan held-out: posisi P 1,000, R 0,898, F1 0,946 [0,894; 1,000]; ketat F1 0,591. Penyebab ketat rendah: pada N07 dan R02
kolom varietas diambil dari kolom "Keunggulan varietas" (model embedding peka huruf besar-kecil). Setelah diperbaiki
(commit ac4f2e4), rerun N07 dan R02: semua kolom benar, F1 ketat 1,000. Normalisasi mengubah 111 dari 521 sel (koma desimal,
tanda rentang, huruf kecil sesuai kosakata template), tidak ada yang berubah makna.

### 6.7 Foto Commons (160 foto, run UI 1 November, terkoreksi D18)
| Metrik | Label sumber Commons | Label tinjauan visual |
|---|---|---|
| Macro-F1, V2 nama file saja | 0,314 | 0,353 |
| **Macro-F1, V3 (= V1)** | **0,640** [0,531; 0,728] | 0,564 [0,474; 0,640] |
| Top-1 pada foto KNOWN | 0,727 [0,635; 0,812] | 0,795 [0,709; 0,874] |
| Recall OTHER | 0,667 | 0,675 |
| Non-KNOWN diprediksi KNOWN | 19 / 61 | 30 / 75 |
| Presisi AUTO_LINK, semua | 64/87 = 0,736 | 59/87 = 0,678 |
| nama informatif | 35/36 = 0,972 | 34/36 = 0,944 |
| **nama netral** | **29/45 = 0,644** | 25/45 = 0,556 |
| nama menyesatkan | 0/6 | 0/6 |

**Koreksi mock (4 Nov 2026).** Pada run UI 1 Nov, 19 dari 160 foto dijawab **mock**, yaitu jawaban tiruan yang dulu dipakai
diam-diam saat panggilan model gagal. Rinciannya 8 bernama informatif, 7 menyesatkan, dan 4 netral. Kode diperbaiki lewat D18:
kegagalan model sekarang menjadi error dan tidak lagi diganti mock. Ke-19 foto itu lalu dijalankan ulang dengan model dan
prompt yang sama; satu foto gagal di percobaan pertama, lalu berhasil di percobaan kedua. Tabel di atas sudah memakai hasil
terkoreksi (`hasil_ui/2026-11-04_koreksi_mock/`, salinan di `dataset_eksperimen/4_hasil_sistem/H_koreksi_foto_commons_D18/`).
Perbandingan sebelum dan sesudah koreksi (label sumber):

| Metrik | Sebelum (dengan mock) | Sesudah |
|---|---|---|
| Macro-F1 | 0,692 | 0,640 |
| Top-1 KNOWN | 0,758 | 0,727 |
| AUTO_LINK semua | 67/94 = 0,713 | 64/87 = 0,736 |
| nama netral | 29/44 = 0,659 | 29/45 = 0,644 |
| nama menyesatkan | 0/11 | 0/6 (26 dari 32 ke review, 13 di antaranya benar secara visual) |

Mock membuat klasifikasi tampak lebih baik, karena varietas ditebak dari nama file informatif. Namun mock juga menambah
tautan salah pada nama menyesatkan. Foto Indonesia dan semua hasil atribut tidak terdampak.

V3 vs V2 macro-F1 +0,326 [0,209; 0,435]. Ada 16 tautan otomatis yang salah pada nama netral:
- 10 dari varietas tidak terdaftar yang mirip, lalu dipaksa masuk ke kolom terdaftar (Scotch Bonnet, Carolina Reaper, dan
  Moruga Scorpion -> Habanero; Banana Pepper -> Hungarian Wax atau Cabai Rawit; Shishito -> Cabai Korea);
- 4 karena salah memilih varietas terdaftar (Cayenne -> Cabai Rawit atau Jalapeno; Paprika -> Cabai Rawit; Serrano -> Jalapeno);
- 2 dari foto tak jelas yang tetap ditautkan.

### 6.8 Foto Indonesia dan gabungan
Gold foto Indonesia = isian peneliti (4 Nov 2026). Semua 12 foto dinilai. Tidak ada foto UNCERTAIN di gold, jadi untuk foto
Indonesia dipakai macro-F1 atas kelas yang ada di gold (KNOWN, OTHER); macro-F1 tiga kelas dicantumkan sebagai pembanding.

| Himpunan | Keputusan | Status benar | Macro-F1 3 kelas | Macro-F1 KNOWN/OTHER | Top-1 KNOWN | AUTO_LINK benar |
|---|---|---|---|---|---|---|
| Indonesia S01 | 12 | 8/12 | 0,519 | 0,778 | 0,750 | 5/8 = 0,625 |
| Indonesia S02 | 12 | 8/12 | 0,536 | 0,804 | 0,750 | 6/8 = 0,750 |
| Indonesia S03 | 12 | 7/12 | 0,370 | 0,556 | 0,833 | 4/8 = 0,500 |
| Indonesia, 3 run | 36 | 23/36 | 0,470 | 0,706 | 0,773 | 15/24 = 0,625 |
| Commons 160 (terkoreksi) | 160 | 108/160 | 0,640 | 0,640 | 0,727 | 64/87 = 0,736 |
| **Gabungan** | **196** | **131/196** | **0,632** | - | **0,736** | **79/111 = 0,712** |

Pola hasilnya (gold peneliti):
- Empat foto Katokkon dan foto buah Kopay selalu benar.
- Daun Gendot dan foto buah Gendot (`p9vb...`) selalu dibaca Katokkon.
- Foto cabai besar (`C. annuum ...`) ditautkan sebagai Cabai tanjung (S01, S03) atau Kopay (S02), dengan keyakinan 0,85-0,95.
- Foto daun *C. chinense* + *C. annuum* ditautkan sebagai Katokkon di S01 dan S03.
- Di S03, buah Domba yang terdaftar justru dianggap OTHER.

Sampelnya kecil (12 foto unik dipakai di 3 run), dan varietas 3 foto hanya dari tinjauan visual, jadi buktinya lemah.

Presisi nama netral tetap 0,644 karena tidak ada foto Indonesia bernama netral. Hasil dengan gold lama (10 foto per run): `hasil_eksperimen/foto_indonesia/arsip_gold_lama/`.

**Skor workbook akhir gabungan** (`skrip/skor_workbook_gabungan.py`). Keluaran sistem adalah satu workbook: baris karakter
diisi dari spreadsheet, sedangkan baris Gambar diisi link foto. Skor ini menilai keduanya dengan satuan yang sama, yaitu satu
sel atribut atau satu link foto (benar / salah tulis / terlewat):

| Run | Atribut F1 | Foto F1 | Gabungan P / R / F1 |
|---|---|---|---|
| Indonesia S01-S03 | 0,906 (212 benar, 0 salah, 44 terlewat) | 0,522 (12/12/10) | 0,949 / 0,806 / **0,872** |
| Commons F1-F8 (spreadsheet hanya nama varietas) | - | 0,677 (63/24/36) | 0,724 / 0,636 / **0,677** |
| **Semua run** | 0,906 | 0,647 (75/36/46) | 0,889 / 0,761 / **0,820** |

Link foto yang salah (36): 18 foto OTHER ditautkan, 4 foto UNCERTAIN ditautkan, 10 salah varietas, dan 4 salah bagian tanaman
(1 Commons: `habanero_buah_053.jpg`, foto daun ditautkan ke Gambar Buah; 3 Indonesia). Gold bagian Commons dan seluruh gold
foto Indonesia memakai isian peneliti (4 Nov 2026). Riwayat skor semua run: 0,838 (gold lama) -> 0,835 (gold bagian Commons)
-> 0,820 (ditambah gold Indonesia peneliti). Sel atribut tidak pernah salah tulis; kesalahannya berupa
sel yang terlewat, terutama pada header bertingkat S03.

**Gold bagian tanaman (4 Nov 2026).** Bagian tanaman 160 foto Commons sekarang memakai anotasi buta peneliti
(`data_evaluasi/gold/bagian_foto_commons/gold_bagian_commons.csv`, dibuat dari `lembar_bagian_160.xlsx` tanpa nama file,
label lama, maupun prediksi). Hasil anotasi: BUAH 128, TANAMAN_UTUH 12, DAUN 10, BUNGA 7, LAIN 3. Bagian dianggap benar
bila sama dengan bagian utama atau bagian kedua yang diisi peneliti; 11 foto TANAMAN_UTUH tanpa bagian kedua dan 3 foto LAIN
tidak dinilai. Akurasi bagian tanaman sistem: **140/146 = 0,959** (foto yang ditautkan otomatis 79/80 = 0,988). Per bagian:
BUAH 128/128, BUNGA 7/7, DAUN 5/10 (empat foto daun dibaca BUAH, satu BUNGA). Kesesuaian dengan label bagian lama (dari judul foto)
135/160. Rincian: `data_evaluasi/hasil_eksperimen/bagian_foto/hasil_skor.md` (skrip `skor_bagian_foto_commons.py`).

### 6.9 Skema kanonik dinamis (fitur, hasil kelayakan)
Dengan saklar aktif, R01, N07, N09, R02 diproses berurutan tiga kali dari database kosong: 84-85 atribut tak berpadanan
menghasilkan 40 baris provisional; workbook berikutnya sebagian besar memakai ulang baris itu. Tidak ada baris yang menduplikasi
baris template; F1 baris template tidak turun; kesamaan label antarulangan Jaccard 0,70-0,78. Ini hasil kelayakan satu urutan,
bukan metode tervalidasi.

### 6.10 Pilot foto Berita Resmi PVT (tidak dipakai di paper)
40 foto, dua kondisi: kartu nama terlihat Top-1 20/30; kartu ditutup Top-1 **0/30**, UNCERTAIN 37/40, 3 tautan otomatis salah
(keyakinan 0,88-0,90). Varietas dikenali dari tulisan kartu, bukan tanaman. Rincian: `data_evaluasi/pilot_foto_pvt/LAPORAN_PILOT.md`.

---

## 7. Status pekerjaan (revisi masukan dosen)

| Poin dosen | Status |
|---|---|
| 1 Gold tidak independen | anotasi buta oleh peneliti sendiri (kappa 0,97); anotator independen belum |
| 2 Statistik per workbook | **selesai** (draf v8/v9) |
| 3 Akurasi isi spreadsheet | **selesai** (draf v9) |
| 4 Pembanding dari literatur | belum |
| 5 LLM open-weight | belum |
| 6, 7, 11, 12 | ditunda sesuai keputusan peneliti |
| 8 Klaim multimodal | dipertahankan; spreadsheet asli GRIN sedang diuji (di bawah) |
| 9 Butir ambigu | **selesai** |
| 10 Beban review | **selesai** |

Selesai 4-8 Nov:
- Koreksi mock D18 (19 foto dijalankan ulang; paper v10/v11).
- Pembersihan data ke level varietas D19 (4 tahap; terakhir Gendot, Domba, Bhut Jolokia, GRIN Poblano).
- Gold kanonik 317 foto PVT D21 (bagian tanaman menunggu verifikasi peneliti di `lembar_gold_kanonik_foto_pvt.xlsx`).
- Embedding diganti ke bge-m3 D22, run atribut end-to-end 3 pengulangan (6A.2).
- Run ulang foto dengan deskripsi varietas D20 dan desain nama file berpasangan D23 (6A.4-6A.6).
- Rencana run GRIN dihentikan: GRIN tinggal Hungarian Wax setelah D19.

Selesai 12 Nov:
- Visi dua tahap D24 (model buta nama berkas) dan run ulang semua 271 foto D23 + ablasi fusi (6A.7).

Hal terbuka:
- Angka di draf paper masih versi v11 (data dan sistem lama).
- Nama berkas yang menyebut varietas tidak terdaftar belum dipakai sebagai sinyal CANDIDATE (D24).
- Foto baru dijalankan 1x per kondisi; perlu >= 3 ulangan untuk klaim statistik.
- Uji paritas lewat jalur produksi penuh (Drive + `vision_hook` + KMS) belum dijalankan.
- Gold atribut P01/P02 belum diverifikasi (144 butir perlu diputuskan).
- Diagram alur (Fig. 1): tambahkan panah registry/nama file ke model visi, lalu ganti label "curator-approved" (baris baru
  langsung ditulis sebagai provisional).
- Paper masih menyajikan foto Indonesia terpisah dari foto Commons; belum diputuskan apakah tabelnya digabung.
- 31 baris kanonik provisional di database KMS dari rerun N07/R02 (4 Nov) dibiarkan sesuai keputusan peneliti.
- `data_evaluasi/hasil_eksperimen/akurasi_sel/cek_normalisasi.xlsx`: kolom konfirmasi makna belum diisi peneliti.
- Hitung ulang aturan tautan otomatis yang lebih ketat (nama netral -> review, ambang > 0,85) belum dikerjakan.

---

## 8. Peta berkas

### Dokumen
| Berkas | Isi |
|---|---|
| `docs/paper/paper_ieee_draft_v11.pdf` | paper terbaru (7 halaman; foto terkoreksi D18, gold foto Indonesia dan gold bagian dari peneliti) |
| `docs/paper/DAFTAR_PERBAIKAN_PAPER.txt` | masukan dosen |
| `docs/SKENARIO_EKSPERIMEN.md`, `docs/RENCANA_EVALUASI.md` | protokol dan definisi metrik awal |
| `dataset_eksperimen/KETERANGAN_DATA.txt`, `DESKRIPSI_PEMBUATAN_DAN_TUJUAN_DATA.txt` | rincian semua data dan run |

### Hasil
| Berkas (di `data_evaluasi/hasil_eksperimen/`) | Isi |
|---|---|
| `analisis_paper.md` | varian, uji berpasangan, retrieval, latency, foto |
| `analisis_revisi_dosen.md` | per workbook, CI per workbook, sensitivitas, beban review |
| `akurasi_sel/akurasi_sel.md`, `cek_normalisasi.xlsx` | akurasi sel dan cek normalisasi |
| `foto_indonesia/hasil_skor.md` | foto Indonesia dan gabungan |
| `rincian_autolink_netral.xlsx` | 64 foto bernama netral beserta gambar (terkoreksi) |
| `workbook_gabungan/hasil_skor.md` | skor workbook gabungan (sel atribut + link foto) |
| `hasil_ui/2026-11-04_koreksi_mock/`, `ulang_foto_mock/` | hasil foto terkoreksi dan rerun 19 foto mock |

### Skrip penghitung (di `data_evaluasi/skrip/`, jalankan dari folder `data_evaluasi`)
| Skrip | Menghasilkan |
|---|---|
| `hitung_metrik.py` | rumus metrik inti dan bootstrap |
| `analisis_paper.py` | `analisis_paper.md` |
| `analisis_revisi_dosen.py` | `analisis_revisi_dosen.md` |
| `akurasi_sel.py` | `akurasi_sel/` dan `gold/kunci_sel/` |
| `skor_foto_indonesia.py` | `foto_indonesia/hasil_skor.md` |
| `rincian_autolink_netral.py` | `rincian_autolink_netral.xlsx` |
| `skor_foto_grin.py` | skor run GRIN (setelah run selesai) |
| `koreksi_foto_mock.py` | mengganti 19 baris mock dengan hasil rerun -> `hasil_ui/2026-11-04_koreksi_mock/` |
| `skor_workbook_gabungan.py` | `workbook_gabungan/` |
| `kumpulkan_dataset_eksperimen.py` | menyalin input/hasil ke `dataset_eksperimen/` (`--tambah-bge-m3`, `--tambah-foto-ulang`) |
| `banding_embedding.py` | `hasil_retrieval/banding_embedding/` (Hit@k, MRR per model) |
| `harness_vps.py` | run pipeline produksi tanpa UI (`--tanpa-foto` untuk run atribut saja) |
| `skor_atribut_e2e.py` | `skor_atribut_e2e_bge-m3/` (run baru vs run pembanding) |
| `uji_visi_commons_vps.py` | klasifikasi foto lewat langkah `vision_hook` tanpa tulis KMS (`--kanonik` = registri + deskripsi D20; `--mode two_stage/single_call` D24; `--db-dari-meta` mengunci varietas DB ke run lama) |
| `ablasi_fusi_m2.py` | hitung ulang tindakan fusi dari jawaban visual tercatat dengan aturan lama/baru (ablasi D24) |
| `hasil_eksperimen/foto_two_stage_2026-11-12/job_m2.sh` | run ulang semua set foto D23 dengan visi dua tahap (kelompok A/B/C paralel) |
| `skor_foto_ulang.py` | `foto_ulang_2026-11-07/skor/` (foto + workbook gabungan) |
| `buat_nama_file_berpasangan.py`, `skor_nama_file_berpasangan.py` | data, gold, dan skor desain nama file berpasangan (D23) |
| `gold_kanonik_foto_pvt.py` | lembar verifikasi dan gold kanonik foto PVT (D21) |
