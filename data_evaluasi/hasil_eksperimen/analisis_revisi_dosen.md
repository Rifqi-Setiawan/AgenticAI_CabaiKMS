# Analisis revisi paper (masukan dosen poin 2, 9, 10)

Sumber: harness rep1 (S1/S2/S4: 2026-10-31 dan 2026-11-01_bc3c21b; S3: 2026-11-02_S3). Gold `gold/final/gold_semua_dataset_final.csv`. tau S2+tau = 0.3857 (sama dengan analisis_paper.py). Bootstrap 10000 ulangan, seed 20261103.

## Poin 2a. F1 per workbook (butir inti)

| Workbook | Split | T / N | S1 | S2 | S2+tau | S3 | S4 | S4 P | S4 R | S4 NULL R |
|---|---|---|---|---|---|---|---|---|---|---|
| R01 | dev | 1 / 13 | 0.000 | 0.143 | 0.222 | 0.667 | 0.667 | 0.500 | 1.000 | 0.923 |
| S01 | dev | 20 / 1 | 0.333 | 0.537 | 0.500 | - | 0.974 | 1.000 | 0.950 | 1.000 |
| S02 | dev | 22 / 4 | 0.000 | 0.383 | 0.450 | - | 1.000 | 1.000 | 1.000 | 1.000 |
| S03 | dev | 28 / 2 | 0.133 | 0.246 | 0.250 | - | 0.783 | 1.000 | 0.643 | 1.000 |
| R02 | held-out | 18 / 32 | 0.615 | 0.418 | 0.491 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| N07 | held-out | 20 / 45 | 0.710 | 0.405 | 0.542 | 1.000 | 0.974 | 1.000 | 0.950 | 1.000 |
| N08 | held-out | 9 / 12 | 0.364 | 0.207 | 0.222 | 1.000 | 0.875 | 1.000 | 0.778 | 1.000 |
| N09 | held-out | 24 / 48 | 0.629 | 0.375 | 0.459 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |

Catatan: F1 R01 dihitung dari 1 butir bertarget sehingga hanya bernilai 0 atau 1; S3 tidak dijalankan pada S01 sampai S03.

### Rata-rata F1 per workbook (macro) dan konsistensi arah, held-out

| Varian | F1 gabungan (micro) | Rata-rata F1 per workbook | Min | Maks | S4 lebih tinggi di | S4 sama |
|---|---|---|---|---|---|---|
| S1 | 0.621 | 0.579 | 0.364 | 0.710 | 4 dari 4 | 0 dari 4 |
| S2 | 0.377 | 0.351 | 0.207 | 0.418 | 4 dari 4 | 0 dari 4 |
| S2+tau | 0.460 | 0.429 | 0.222 | 0.542 | 4 dari 4 | 0 dari 4 |
| S3 | 1.000 | 1.000 | 1.000 | 1.000 | 0 dari 4 | 2 dari 4 |
| S4 | 0.978 | 0.962 | 0.875 | 1.000 | - | - |

## Poin 2b. Selang kepercayaan F1: bootstrap per butir vs per workbook

| Himpunan | Varian | F1 | CI per butir | CI per workbook (cluster) |
|---|---|---|---|---|
| held-out (4 workbook) | S1 | 0.621 | [0.505, 0.725] | [0.500, 0.688] |
| held-out (4 workbook) | S2 | 0.377 | [0.302, 0.451] | [0.299, 0.411] |
| held-out (4 workbook) | S2+tau | 0.460 | [0.372, 0.546] | [0.335, 0.518] |
| held-out (4 workbook) (4 wb) | S3 | 1.000 | [1.000, 1.000] | [1.000, 1.000] |
| held-out (4 workbook) | S4 | 0.978 | [0.951, 1.000] | [0.929, 1.000] |
| dev (4 workbook) | S1 | 0.156 | [0.053, 0.265] | [0.000, 0.320] |
| dev (4 workbook) | S2 | 0.352 | [0.250, 0.454] | [0.225, 0.494] |
| dev (4 workbook) | S2+tau | 0.372 | [0.264, 0.481] | [0.246, 0.481] |
| dev (4 workbook) | S4 | 0.909 | [0.852, 0.955] | [0.776, 0.993] |
| semua (8 workbook) | S1 | 0.422 | [0.328, 0.508] | [0.211, 0.600] |
| semua (8 workbook) | S2 | 0.368 | [0.307, 0.428] | [0.301, 0.421] |
| semua (8 workbook) | S2+tau | 0.425 | [0.355, 0.492] | [0.332, 0.492] |
| semua (8 workbook) (5 wb) | S3 | 0.993 | [0.977, 1.000] | [0.960, 1.000] |
| semua (8 workbook) | S4 | 0.945 | [0.914, 0.971] | [0.873, 0.990] |

CI per workbook pada stratum semantik held-out: S1 0.000 [0.000, 0.000]; S2 0.189 [0.134, 0.220]; S2+tau 0.228 [0.151, 0.270]; S4 0.960 [0.893, 1.000].

## Poin 2c. Uji berpasangan held-out dengan resampel workbook (Holm)

| Perbandingan | Selisih F1 | CI 95% per workbook | p cluster | p Holm |
|---|---|---|---|---|
| S4 vs S1 | +0.357 | [+0.291, +0.438] | 0.0000 | 0.0000 |
| S4 vs S2 | +0.602 | [+0.576, +0.633] | 0.0000 | 0.0000 |
| S4 vs S2+tau | +0.518 | [+0.462, +0.600] | 0.0000 | 0.0000 |
| S4 vs S3 (eksploratori) | -0.022 | [-0.071, +0.000] | 0.1260 | - |

Dengan hanya 4 workbook held-out, resampel per workbook hanya punya 35 kombinasi berbeda, jadi CI kasar. p cluster bernilai 0 karena S4 lebih tinggi pada setiap workbook sehingga semua resampel positif; ini setara dengan pernyataan arah per workbook (tabel 2a), bukan bukti yang lebih kuat. Uji eksak yang paling jujur untuk 4 dari 4 workbook adalah uji tanda satu sisi, p = 0,0625; dengan 8 workbook (dev + held-out) dan S4 lebih tinggi di semuanya, p = 0,0039.

S4 lebih tinggi dari S1/S2/S2+tau pada 8/8/8 dari 8 workbook.

### Leave-one-workbook-out, held-out (F1 bila satu workbook dibuang)

| Dibuang | S1 | S2 | S2+tau | S4 |
|---|---|---|---|---|
| R02 | 0.623 | 0.364 | 0.450 | 0.971 |
| N07 | 0.583 | 0.365 | 0.429 | 0.980 |
| N08 | 0.652 | 0.397 | 0.495 | 0.992 |
| N09 | 0.618 | 0.378 | 0.460 | 0.967 |

## Poin 9. Sensitivitas terhadap 19 butir AMBIGUOUS/COMPOSITE

Butir ekstra yang dinilai: 19 (semua di held-out: R02 4, N07 5, N08 2, N09 8).
Longgar: butir ekstra dihitung bertarget dan benar bila prediksi termasuk salah satu kunci yang mungkin. Pesimis: butir ekstra dihitung bertarget dan tidak pernah benar (batas bawah). Abstain benar: butir ekstra diperlakukan seperti NO_MATCH, karena sumber tidak cukup untuk memilih satu baris; NULL dihitung penolakan yang benar, baris di luar kemungkinan dihitung salah tulis, dan memilih salah satu kunci yang mungkin dibuang dari skor.

| Himpunan | Skenario | Varian | n target / NULL | P | R | F1 [CI per workbook] |
|---|---|---|---|---|---|---|
| held-out | inti (paper) | S1 | 71 / 137 | 1.000 | 0.451 | 0.621 [0.500, 0.688] |
| held-out | inti (paper) | S2 | 71 / 137 | 0.254 | 0.732 | 0.377 [0.299, 0.411] |
| held-out | inti (paper) | S2+tau | 71 / 137 | 0.345 | 0.690 | 0.460 [0.335, 0.518] |
| held-out | inti (paper) | S4 | 71 / 137 | 1.000 | 0.958 | 0.978 [0.929, 1.000] |
| held-out | longgar | S1 | 90 / 137 | 1.000 | 0.356 | 0.525 [0.415, 0.583] |
| held-out | longgar | S2 | 90 / 137 | 0.272 | 0.678 | 0.389 [0.322, 0.426] |
| held-out | longgar | S2+tau | 90 / 137 | 0.365 | 0.633 | 0.463 [0.355, 0.520] |
| held-out | longgar | S4 | 90 / 137 | 1.000 | 0.778 | 0.875 [0.829, 0.894] |
| held-out | pesimis | S1 | 90 / 137 | 1.000 | 0.356 | 0.525 [0.415, 0.583] |
| held-out | pesimis | S2 | 90 / 137 | 0.232 | 0.578 | 0.331 [0.264, 0.367] |
| held-out | pesimis | S2+tau | 90 / 137 | 0.314 | 0.544 | 0.398 [0.289, 0.457] |
| held-out | pesimis | S4 | 90 / 137 | 0.971 | 0.756 | 0.850 [0.811, 0.884] |
| held-out | abstain benar | S1 | 71 / 156 | 1.000 | 0.451 | 0.621 [0.500, 0.688] |
| held-out | abstain benar | S2 | 71 / 147 | 0.242 | 0.732 | 0.364 [0.289, 0.400] |
| held-out | abstain benar | S2+tau | 71 / 148 | 0.331 | 0.690 | 0.447 [0.323, 0.509] |
| held-out | abstain benar | S4 | 71 / 154 | 1.000 | 0.958 | 0.978 [0.929, 1.000] |
| semua | inti (paper) | S1 | 142 / 157 | 1.000 | 0.268 | 0.422 [0.211, 0.600] |
| semua | inti (paper) | S2 | 142 / 157 | 0.273 | 0.563 | 0.368 [0.301, 0.421] |
| semua | inti (paper) | S2+tau | 142 / 157 | 0.352 | 0.535 | 0.425 [0.332, 0.492] |
| semua | inti (paper) | S4 | 142 / 157 | 0.992 | 0.901 | 0.945 [0.873, 0.990] |
| semua | longgar | S1 | 161 / 157 | 1.000 | 0.236 | 0.382 [0.203, 0.515] |
| semua | longgar | S2 | 161 / 157 | 0.285 | 0.553 | 0.376 [0.311, 0.428] |
| semua | longgar | S2+tau | 161 / 157 | 0.365 | 0.522 | 0.430 [0.342, 0.492] |
| semua | longgar | S4 | 161 / 157 | 0.992 | 0.807 | 0.890 [0.834, 0.943] |
| semua | pesimis | S1 | 161 / 157 | 1.000 | 0.236 | 0.382 [0.203, 0.515] |
| semua | pesimis | S2 | 161 / 157 | 0.256 | 0.497 | 0.338 [0.283, 0.394] |
| semua | pesimis | S2+tau | 161 / 157 | 0.330 | 0.472 | 0.389 [0.313, 0.449] |
| semua | pesimis | S4 | 161 / 157 | 0.977 | 0.795 | 0.877 [0.821, 0.936] |
| semua | abstain benar | S1 | 142 / 176 | 1.000 | 0.268 | 0.422 [0.211, 0.600] |
| semua | abstain benar | S2 | 142 / 167 | 0.264 | 0.563 | 0.360 [0.296, 0.413] |
| semua | abstain benar | S2+tau | 142 / 168 | 0.342 | 0.535 | 0.418 [0.330, 0.483] |
| semua | abstain benar | S4 | 142 / 174 | 0.992 | 0.901 | 0.945 [0.873, 0.990] |

### Apa yang dilakukan tiap varian pada 19 butir itu

| Varian | Memilih salah satu kunci yang mungkin | Memilih baris lain | NULL (abstain) |
|---|---|---|---|
| S1 (n=19) | 0 | 0 | 19 |
| S2 (n=19) | 9 | 10 | 0 |
| S2+tau (n=19) | 8 | 6 | 5 |
| S3 (n=19) | 3 | 0 | 16 |
| S4 (n=19) | 2 | 0 | 17 |

| Butir | Workbook | Status | Kunci yang mungkin | S4 | S2 |
|---|---|---|---|---|---|
| Orientasi pedunkulus | R02 | AMBIGUOUS | posisi_bunga, posisi_buah_masak | NULL | tekstur_daun |
| Leaf size as recorded | R02 | COMPOSITE | panjang_daun, lebar_daun | NULL | lebar_daun |
| Warna benang sari | R02 | AMBIGUOUS | warna_tangkai_sari, warna_kepala_sari | NULL | warna_tangkai_sari |
| Tipe berbuah | R02 | AMBIGUOUS | posisi_buah_muda, posisi_buah_masak | NULL | tekstur_daun |
| benang sari | N07 | AMBIGUOUS | warna_tangkai_sari, warna_kepala_sari | NULL | warna_kepala_sari |
| Warna benangsari | N07 | AMBIGUOUS | warna_tangkai_sari, warna_kepala_sari | NULL | warna_tangkai_sari |
| Panjang buah | N07 | AMBIGUOUS | panjang_buah_muda, panjang_buah_masak | panjang_buah_masak | panjang_kelopak_buah_muda |
| Ukuran buah | N07 | AMBIGUOUS | panjang_buah_muda, panjang_buah_masak | NULL | panjang_tangkai_buah_muda |
| Ukuran daun | N07 | COMPOSITE | panjang_daun, lebar_daun | NULL | lebar_daun |
| Leaf size as recorded | N08 | AMBIGUOUS | panjang_daun, lebar_daun | NULL | panjang_daun |
| Corolla diameter | N08 | AMBIGUOUS | lebar_mahkota_bunga, panjang_mahkota | NULL | luas_daun |
| Benang sari | N09 | AMBIGUOUS | warna_tangkai_sari, warna_kepala_sari | NULL | warna_tangkai_sari |
| Warna benang sari | N09 | AMBIGUOUS | warna_tangkai_sari, warna_kepala_sari | NULL | warna_tangkai_sari |
| Panjang buah | N09 | AMBIGUOUS | panjang_buah_muda, panjang_buah_masak | NULL | panjang_kelopak_buah_muda |
| Tipe Berbuah | N09 | AMBIGUOUS | posisi_buah_muda, posisi_buah_masak | NULL | tekstur_daun |
| Ukuran daun | N09 | COMPOSITE | panjang_daun, lebar_daun | NULL | lebar_daun |
| Orientasi pedunkulus | N09 | AMBIGUOUS | posisi_bunga, posisi_buah_masak | NULL | tekstur_daun |
| Ukuran buah | N09 | AMBIGUOUS | panjang_buah_muda, panjang_buah_masak | NULL | panjang_tangkai_buah_muda |
| Ukuran buah Panjang | N09 | AMBIGUOUS | panjang_buah_muda, panjang_buah_masak | panjang_buah_masak | panjang_tangkai_buah_muda |

## Poin 10. Beban review menurut alasan sistem

REVIEW_NULL = sistem mengusulkan tidak ada padanan (NULL) dan meminta konfirmasi kurator. REVIEW_RAGU = sistem mengusulkan baris tetapi tidak cukup yakin untuk menulis otomatis.

| Himpunan | Butir | AUTO_ACCEPT | REVIEW_NULL | REVIEW_RAGU | Lain |
|---|---|---|---|---|---|
| dev, inti | 88 | 61 (69%) | 27 (31%) | 0 | 0 |
| dev, termasuk AMB/COMP | 88 | 61 (69%) | 27 (31%) | 0 | 0 |
| held-out, inti | 205 | 68 (33%) | 137 (67%) | 0 | 0 |
| held-out, termasuk AMB/COMP | 224 | 70 (31%) | 154 (69%) | 0 | 0 |
| semua, inti | 293 | 129 (44%) | 164 (56%) | 0 | 0 |
| semua, termasuk AMB/COMP | 312 | 131 (42%) | 181 (58%) | 0 | 0 |

### REVIEW_NULL menurut status gold (semua workbook, termasuk AMB/COMP)

| Status gold | REVIEW_NULL | AUTO_ACCEPT benar | AUTO_ACCEPT salah |
|---|---|---|---|
| NO_MATCH | 150 | 0 | 1 |
| ONE_TO_ONE | 14 | 128 | 0 |
| AMBIGUOUS | 14 | 2 | 0 |
| COMPOSITE | 3 | 0 | 0 |

### Beban review per workbook (butir inti)

| Workbook | Butir | REVIEW_NULL | di antaranya gold NO_MATCH | di antaranya bertarget |
|---|---|---|---|---|
| R01 | 13 | 11 | 11 | 0 |
| S01 | 21 | 2 | 1 | 1 |
| S02 | 25 | 3 | 3 | 0 |
| S03 | 29 | 11 | 1 | 10 |
| R02 | 49 | 31 | 31 | 0 |
| N07 | 64 | 45 | 44 | 1 |
| N08 | 20 | 13 | 11 | 2 |
| N09 | 72 | 48 | 48 | 0 |

Keyakinan pada AUTO_ACCEPT: 0.85, 0.90, 0.95, 0.98, 0.99, 1.00. Tidak ada usulan baris yang ditahan karena keyakinan rendah.

Label unik di antrean REVIEW_NULL (nama sumber dinormalisasi): semua 164 butir -> 106 label; held-out 137 butir -> 80 label (35 label muncul lebih dari sekali). Bila keputusan 'tanpa padanan' disimpan per label (mis. lewat katalog atribut/skema dinamis), kurator cukup memutuskan sekali per label.

