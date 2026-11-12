# Analisis lanjut (sementara)

Sumber atribut: harness rep1; N08 memakai berkas varian (D4); S04 ditolak sistem dan tidak masuk. Paired bootstrap 10000 ulangan, seed 20261101; koreksi Holm pada perbandingan confirmatory.

## 1. Mapping F1 per partisi dan varian

| Partisi | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |
|---|---|---|---|---|---|---|
| Held-out (R02, N07, N08, N09) | S4 | 71 / 137 | 1.000 | 0.958 | 0.978 (0.950 sampai 1.000) | 1.000 |
| Held-out (R02, N07, N08, N09) | S1 | 71 / 137 | 1.000 | 0.451 | 0.621 (0.489 sampai 0.723) | 1.000 |
| Held-out (R02, N07, N08, N09) | S2 | 71 / 137 | 0.254 | 0.732 | 0.377 (0.301 sampai 0.447) | 0.022 |
| Dev (R01, S01, S02, S03) | S4 | 71 / 20 | 0.984 | 0.845 | 0.909 (0.852 sampai 0.953) | 0.950 |
| Dev (R01, S01, S02, S03) | S1 | 71 / 20 | 1.000 | 0.085 | 0.156 (0.055 sampai 0.268) | 1.000 |
| Dev (R01, S01, S02, S03) | S2 | 71 / 20 | 0.318 | 0.394 | 0.352 (0.248 sampai 0.453) | 0.150 |
| Semua | S4 | 142 / 157 | 0.992 | 0.901 | 0.945 (0.915 sampai 0.970) | 0.994 |
| Semua | S1 | 142 / 157 | 1.000 | 0.268 | 0.422 (0.333 sampai 0.511) | 1.000 |
| Semua | S2 | 142 / 157 | 0.273 | 0.563 | 0.368 (0.309 sampai 0.427) | 0.038 |

## 2. Stratum kesulitan (lookup = dihasilkan exact_name pada S4; semantik = sisanya)

| Partisi | Stratum | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |
|---|---|---|---|---|---|---|---|
| Held-out (R02, N07, N08, N09) | lookup | S4 | 32 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Held-out (R02, N07, N08, N09) | lookup | S2 | 32 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Held-out (R02, N07, N08, N09) | semantik | S4 | 39 / 137 | 1.000 | 0.923 | 0.960 (0.903 sampai 1.000) | 1.000 |
| Held-out (R02, N07, N08, N09) | semantik | S2 | 39 / 137 | 0.116 | 0.513 | 0.189 (0.117 sampai 0.258) | 0.022 |
| Dev (R01, S01, S02, S03) | lookup | S4 | 6 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Dev (R01, S01, S02, S03) | lookup | S2 | 6 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Dev (R01, S01, S02, S03) | semantik | S4 | 65 / 20 | 0.982 | 0.831 | 0.900 (0.840 sampai 0.952) | 0.950 |
| Dev (R01, S01, S02, S03) | semantik | S2 | 65 / 20 | 0.268 | 0.338 | 0.299 (0.196 sampai 0.405) | 0.150 |
| Semua | lookup | S4 | 38 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Semua | lookup | S2 | 38 / 0 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | - |
| Semua | semantik | S4 | 104 / 157 | 0.989 | 0.865 | 0.923 (0.884 sampai 0.957) | 0.994 |
| Semua | semantik | S2 | 104 / 157 | 0.165 | 0.404 | 0.234 (0.176 sampai 0.290) | 0.038 |

## 3. Uji berpasangan atribut (confirmatory; Holm)

| Himpunan | Perbandingan | Selisih F1 | CI 95% | p mentah | p Holm |
|---|---|---|---|---|---|
| Held-out (R02, N07, N08, N09) | S4 vs S1 (Mapping F1) | +0.357 | +0.258 sampai +0.476 | 0.0000 | 0.0000 |
| Held-out (R02, N07, N08, N09) | S4 vs S2 (Mapping F1) | +0.602 | +0.528 sampai +0.676 | 0.0000 | 0.0000 |
| Held-out (R02, N07, N08, N09) | S4 vs S2 (recall atribut baru) | +0.978 | +0.950 sampai +1.000 | 0.0000 | 0.0000 |
| Semua | S4 vs S1 (Mapping F1) | +0.522 | +0.436 sampai +0.615 | 0.0000 | 0.0000 |
| Semua | S4 vs S2 (Mapping F1) | +0.577 | +0.520 sampai +0.633 | 0.0000 | 0.0000 |
| Semua | S4 vs S2 (recall atribut baru) | +0.955 | +0.920 sampai +0.986 | 0.0000 | 0.0000 |

## 4. Foto (160 foto Commons, hasil UI)

| Himpunan | Perbandingan | Selisih macro-F1 | CI 95% | p mentah | p Holm |
|---|---|---|---|---|---|
| Semua foto (n=160) | V3 vs V1 | +0.000 | +0.000 sampai +0.000 | 1.0000 | 1.0000 |
| Nama file MENYESATKAN (n=32) | V3 vs V2 | +0.259 | -0.014 sampai +0.480 | 0.0724 | 0.1448 |
| Semua foto (n=160) | V3 vs V2 | +0.326 | +0.209 sampai +0.435 | 0.0000 | 0.0000 |

Catatan: V3 dan V1 identik pada pemetaan yang dipakai (tindakan review mempertahankan status visual); perbandingan V3 vs V1 selalu 0.

## 5. Ketepatan tautan otomatis (eksploratori)

| Kondisi nama file | AUTO_LINK | benar | ketepatan | REVIEW (dialihkan) | di antaranya benar |
|---|---|---|---|---|---|
| INFORMATIF | 36 | 35 | 0.972 | 8 | 4 |
| NETRAL | 45 | 29 | 0.644 | 4 | 1 |
| MENYESATKAN | 6 | 0 | 0.000 | 26 | 13 |
| Semua | 87 | 64 | 0.736 | 38 | 18 |
