# Analisis tambahan untuk paper

Gold atribut: `gold/final/gold_semua_dataset_final.csv` (identik dengan gold awal). tau S2+tau = 0.3857 (dituning di dev, maks. Mapping F1).
Butir semantik tanpa kandidat di dump: 0.

## 1. Pemetaan atribut per varian

| Himpunan | Varian | n target / NULL | Precision | Recall | F1 (CI 95%) | Recall NULL |
|---|---|---|---|---|---|---|
| held-out | S1 | 71 / 137 | 1.000 | 0.451 | 0.621 (0.489 sampai 0.723) | 1.000 |
| held-out | S2 | 71 / 137 | 0.254 | 0.732 | 0.377 (0.301 sampai 0.447) | 0.022 |
| held-out | S2+tau | 71 / 137 | 0.345 | 0.690 | 0.460 (0.373 sampai 0.546) | 0.438 |
| held-out | S4 | 71 / 137 | 1.000 | 0.958 | 0.978 (0.950 sampai 1.000) | 1.000 |
| held-out semantik | S1 | 39 / 137 | 0.000 | 0.000 | 0.000 (0.000 sampai 0.000) | 1.000 |
| held-out semantik | S2 | 39 / 137 | 0.116 | 0.513 | 0.189 (0.117 sampai 0.258) | 0.022 |
| held-out semantik | S2+tau | 39 / 137 | 0.155 | 0.436 | 0.228 (0.138 sampai 0.317) | 0.438 |
| held-out semantik | S4 | 39 / 137 | 1.000 | 0.923 | 0.960 (0.903 sampai 1.000) | 1.000 |
| dev | S1 | 71 / 20 | 1.000 | 0.085 | 0.156 (0.055 sampai 0.268) | 1.000 |
| dev | S2 | 71 / 20 | 0.318 | 0.394 | 0.352 (0.248 sampai 0.453) | 0.150 |
| dev | S2+tau | 71 / 20 | 0.365 | 0.380 | 0.372 (0.262 sampai 0.480) | 0.600 |
| dev | S4 | 71 / 20 | 0.984 | 0.845 | 0.909 (0.852 sampai 0.953) | 0.950 |
| semua | S1 | 142 / 157 | 1.000 | 0.268 | 0.422 (0.333 sampai 0.511) | 1.000 |
| semua | S2 | 142 / 157 | 0.273 | 0.563 | 0.368 (0.309 sampai 0.427) | 0.038 |
| semua | S2+tau | 142 / 157 | 0.352 | 0.535 | 0.425 (0.356 sampai 0.496) | 0.459 |
| semua | S4 | 142 / 157 | 0.992 | 0.901 | 0.945 (0.915 sampai 0.970) | 0.994 |
| semua semantik | S1 | 104 / 157 | 0.000 | 0.000 | 0.000 (0.000 sampai 0.000) | 1.000 |
| semua semantik | S2 | 104 / 157 | 0.165 | 0.404 | 0.234 (0.176 sampai 0.290) | 0.038 |
| semua semantik | S2+tau | 104 / 157 | 0.213 | 0.365 | 0.270 (0.199 sampai 0.338) | 0.459 |
| semua semantik | S4 | 104 / 157 | 0.989 | 0.865 | 0.923 (0.884 sampai 0.957) | 0.994 |

## 2. Uji berpasangan held-out (bootstrap 10.000, Holm)

| Perbandingan | Selisih | CI 95% | p Holm |
|---|---|---|---|
| S4 vs S1 F1 | +0.357 | +0.258 sampai +0.476 | 0.0000 |
| S4 vs S2 F1 | +0.602 | +0.528 sampai +0.676 | 0.0000 |
| S4 vs S2+tau F1 | +0.518 | +0.433 sampai +0.604 | 0.0000 |
| S4 vs S2+tau recall NULL | +0.562 | +0.479 sampai +0.645 | 0.0000 |

## 3. Retrieval pada butir semantik bertarget

n = 104; rata-rata kandidat yang dilihat reranker 13.0 (top-8 + header-only fallback).
Hit@1 0.404; Hit@5 0.712; Hit@8 0.779; Hit@semua kandidat 0.865; MRR 0.534.

## 4. Latency per run (detik; median dari pengulangan)

| Dataset | S4 median (n) | S3 median (n) | S3/S4 |
|---|---|---|---|
| R01 | 105 (3) | 106 (3) | 1.02 |
| R02 | 330 (3) | 337 (3) | 1.02 |
| N07 | 425 (3) | 410 (3) | 0.96 |
| N09 | 534 (3) | 501 (3) | 0.94 |
| N08 | 179 (3) | 156 (3) | 0.87 |
| Total | 1573 | 1511 | 0.96 |

Catatan: S4 commit 323f1e4 (31 Okt), S3 commit 6217420 (2 Nov); waktu dinding termasuk antrean provider.

## 5. Foto, gold = label_sumber (n=160; kelas {'KNOWN': 99, 'OTHER': 45, 'UNCERTAIN': 16})

V3: macro-F1 0.640 (0.531 sampai 0.728); Top-1 KNOWN 0.727 (0.635 sampai 0.812).
V2: macro-F1 0.314; Top-1 KNOWN 0.394. V3 vs V2 macro-F1 +0.326 (+0.209 sampai +0.435), p 0.0000.
Recall OTHER 0.667. Forced link: 19 dari 61 foto non-KNOWN diprediksi KNOWN; 15 di antaranya tertaut otomatis.
Matriks V3 (baris gold): {'KNOWN': {'KNOWN': 81, 'OTHER': 15, 'UNCERTAIN': 3}, 'OTHER': {'KNOWN': 15, 'OTHER': 30, 'UNCERTAIN': 0}, 'UNCERTAIN': {'KNOWN': 4, 'OTHER': 6, 'UNCERTAIN': 6}}

| Nama file | Foto | AUTO_LINK | Benar | Precision | REVIEW | CANDIDATE |
|---|---|---|---|---|---|---|
| INFORMATIF | 64 | 36 | 35 | 0.972 | 8 | 20 |
| NETRAL | 64 | 45 | 29 | 0.644 | 4 | 15 |
| MENYESATKAN | 32 | 6 | 0 | 0.000 | 26 | 0 |
| SEMUA | 160 | 87 | 64 | 0.736 | 38 | 35 |

## 5. Foto, gold = tinjauan_visual_ai (n=158; kelas {'KNOWN': 83, 'OTHER': 40, 'UNCERTAIN': 35})

V3: macro-F1 0.564 (0.474 sampai 0.640); Top-1 KNOWN 0.795 (0.709 sampai 0.874).
V2: macro-F1 0.353; Top-1 KNOWN 0.410. V3 vs V2 macro-F1 +0.211 (+0.113 sampai +0.307), p 0.0000.
Recall OTHER 0.675. Forced link: 30 dari 75 foto non-KNOWN diprediksi KNOWN; 25 di antaranya tertaut otomatis.
Matriks V3 (baris gold): {'KNOWN': {'KNOWN': 70, 'OTHER': 12, 'UNCERTAIN': 1}, 'OTHER': {'KNOWN': 13, 'OTHER': 27, 'UNCERTAIN': 0}, 'UNCERTAIN': {'KNOWN': 17, 'OTHER': 11, 'UNCERTAIN': 7}}

| Nama file | Foto | AUTO_LINK | Benar | Precision | REVIEW | CANDIDATE |
|---|---|---|---|---|---|---|
| INFORMATIF | 64 | 36 | 34 | 0.944 | 8 | 20 |
| NETRAL | 64 | 45 | 25 | 0.556 | 4 | 15 |
| MENYESATKAN | 30 | 6 | 0 | 0.000 | 24 | 0 |
| SEMUA | 158 | 87 | 59 | 0.678 | 36 | 35 |

