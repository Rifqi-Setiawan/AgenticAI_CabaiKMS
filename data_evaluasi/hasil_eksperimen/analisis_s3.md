# Baseline S3 (aproksimasi) dibanding S4

S3: pipeline yang sama, tetapi penilai LLM menerima seluruh 60 baris kanonik dalam urutan template (tanpa peringkat retrieval). Tahap pencocokan nama persis tetap berjalan. Bukan 'LLM murni': ini mengisolasi kontribusi penyempitan kandidat oleh retrieval.

Dataset: N07, N08, N09, R01, R02; n butir = 222. S4 dari harness rep1 (2026-10-31); S3 dari tiga pengulangan.

| Himpunan | Varian | n target / tanpa target | Precision | Recall | F1 (CI 95%) | Recall atribut baru |
|---|---|---|---|---|---|---|
| Held-out | S4 | 71 / 137 | 1.000 | 0.958 | 0.978 (0.950 sampai 1.000) | 1.000 |
| Held-out | S3 rep1 | 71 / 137 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 |
| Held-out | S3 rep2 | 71 / 137 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 |
| Held-out | S3 rep3 | 71 / 137 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 |
| Dev (R01) | S4 | 1 / 13 | 0.500 | 1.000 | 0.667 (0.000 sampai 1.000) | 0.923 |
| Dev (R01) | S3 rep1 | 1 / 13 | 0.500 | 1.000 | 0.667 (0.000 sampai 1.000) | 0.923 |
| Dev (R01) | S3 rep2 | 1 / 13 | 0.500 | 1.000 | 0.667 (0.000 sampai 1.000) | 0.923 |
| Dev (R01) | S3 rep3 | 1 / 13 | 0.500 | 1.000 | 0.667 (0.000 sampai 1.000) | 0.923 |
| Semua | S4 | 72 / 150 | 0.986 | 0.958 | 0.972 (0.942 sampai 0.993) | 0.993 |
| Semua | S3 rep1 | 72 / 150 | 0.986 | 1.000 | 0.993 (0.978 sampai 1.000) | 0.993 |
| Semua | S3 rep2 | 72 / 150 | 0.986 | 1.000 | 0.993 (0.978 sampai 1.000) | 0.993 |
| Semua | S3 rep3 | 72 / 150 | 0.986 | 1.000 | 0.993 (0.978 sampai 1.000) | 0.993 |

## Uji berpasangan S4 vs S3 (S3 = tiap pengulangan; bootstrap berpasangan 10.000, Holm per himpunan)

| Himpunan | Perbandingan | Selisih F1 | CI 95% | p mentah | p Holm |
|---|---|---|---|---|---|
| Held-out | S4 vs S3 rep1 | -0.022 | -0.050 sampai +0.000 | 0.1016 | 0.3048 |
| Held-out | S4 vs S3 rep2 | -0.022 | -0.050 sampai +0.000 | 0.1016 | 0.3048 |
| Held-out | S4 vs S3 rep3 | -0.022 | -0.050 sampai +0.000 | 0.1016 | 0.3048 |
| Semua | S4 vs S3 rep1 | -0.021 | -0.049 sampai +0.000 | 0.0944 | 0.2832 |
| Semua | S4 vs S3 rep2 | -0.021 | -0.049 sampai +0.000 | 0.0944 | 0.2832 |
| Semua | S4 vs S3 rep3 | -0.021 | -0.049 sampai +0.000 | 0.0944 | 0.2832 |

Butir dengan prediksi berbeda antara S4 dan S3 pada minimal satu pengulangan: 3 dari 222.
