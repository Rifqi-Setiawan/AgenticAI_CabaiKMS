# Skor pemetaan atribut end-to-end: bge-m3 vs MiniLM

Gold: `gold/final/gold_semua_dataset_final.csv` (butir ONE_TO_ONE dan NO_MATCH). Run bge-m3: `/srv/hermes-control/eval/cabai-ui-experiment/hasil_harness/2026-11-07_bge-m3` (rep [1, 2, 3]). Run MiniLM: `hasil_eksperimen/hasil_harness/2026-10-31` + `hasil_eksperimen/hasil_harness/2026-11-01_bc3c21b` (rep [1, 2, 3]).
Workbook R02, N07, N09 identik di kedua run; N08 dan S01-S03 berubah karena pembersihan level varietas (D19), tetapi nama atributnya sama.

## 1. Pemetaan atribut (rep1, CI 95% bootstrap; rerata antarpengulangan dalam kurung)

| Himpunan | Run | Varian | n target / NULL | Precision | Recall | F1 rep1 (CI 95%) | F1 rerata (min-maks) | Recall NULL |
|---|---|---|---|---|---|---|---|---|
| held-out | bge-m3 | S1 | 71 / 137 | 1.000 | 0.451 | 0.621 (0.484 sampai 0.720) | 0.621 (0.621-0.621) | 1.000 |
| held-out | bge-m3 | S2 | 71 / 137 | 0.283 | 0.817 | 0.420 (0.345 sampai 0.495) | 0.420 (0.420-0.420) | 0.022 |
| held-out | bge-m3 | S4 | 71 / 137 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 (1.000-1.000) | 1.000 |
| held-out | MiniLM | S1 | 71 / 137 | 1.000 | 0.451 | 0.621 (0.489 sampai 0.723) | 0.621 (0.621-0.621) | 1.000 |
| held-out | MiniLM | S2 | 71 / 137 | 0.254 | 0.732 | 0.377 (0.301 sampai 0.447) | 0.377 (0.377-0.377) | 0.022 |
| held-out | MiniLM | S4 | 71 / 137 | 1.000 | 0.958 | 0.978 (0.950 sampai 1.000) | 0.978 (0.978-0.978) | 1.000 |
| held-out input sama (R02, N07, N09) | bge-m3 | S1 | 62 / 125 | 1.000 | 0.484 | 0.652 (0.515 sampai 0.761) | 0.652 (0.652-0.652) | 1.000 |
| held-out input sama (R02, N07, N09) | bge-m3 | S2 | 62 / 125 | 0.297 | 0.887 | 0.445 (0.371 sampai 0.519) | 0.445 (0.445-0.445) | 0.016 |
| held-out input sama (R02, N07, N09) | bge-m3 | S4 | 62 / 125 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 (1.000-1.000) | 1.000 |
| held-out input sama (R02, N07, N09) | MiniLM | S1 | 62 / 125 | 1.000 | 0.484 | 0.652 (0.512 sampai 0.767) | 0.652 (0.652-0.652) | 1.000 |
| held-out input sama (R02, N07, N09) | MiniLM | S2 | 62 / 125 | 0.265 | 0.790 | 0.397 (0.321 sampai 0.472) | 0.397 (0.397-0.397) | 0.016 |
| held-out input sama (R02, N07, N09) | MiniLM | S4 | 62 / 125 | 1.000 | 0.984 | 0.992 (0.972 sampai 1.000) | 0.992 (0.992-0.992) | 1.000 |
| dev (S01-S03) | bge-m3 | S1 | 70 / 7 | 1.000 | 0.086 | 0.158 (0.054 sampai 0.282) | 0.158 (0.158-0.158) | 1.000 |
| dev (S01-S03) | bge-m3 | S2 | 70 / 7 | 0.800 | 0.857 | 0.828 (0.740 sampai 0.907) | 0.828 (0.828-0.828) | 0.286 |
| dev (S01-S03) | bge-m3 | S4 | 70 / 7 | 1.000 | 1.000 | 1.000 (1.000 sampai 1.000) | 1.000 (1.000-1.000) | 1.000 |
| dev (S01-S03) | MiniLM | S1 | 70 / 7 | 1.000 | 0.086 | 0.158 (0.054 sampai 0.282) | 0.158 (0.158-0.158) | 1.000 |
| dev (S01-S03) | MiniLM | S2 | 70 / 7 | 0.360 | 0.386 | 0.372 (0.266 sampai 0.493) | 0.372 (0.372-0.372) | 0.286 |
| dev (S01-S03) | MiniLM | S4 | 70 / 7 | 1.000 | 0.843 | 0.915 (0.857 sampai 0.961) | 0.915 (0.915-0.915) | 1.000 |

## 2. Uji berpasangan bge-m3 vs MiniLM (rep1, butir yang sama, bootstrap 10.000)

| Himpunan | Varian | Selisih F1 | CI 95% | p | Selisih recall NULL | CI 95% |
|---|---|---|---|---|---|---|
| held-out | S2 | +0.043 | +0.000 sampai +0.090 | 0.0508 | +0.000 | -0.029 sampai +0.029 |
| held-out | S4 | +0.022 | +0.000 sampai +0.050 | 0.0946 | +0.000 | +0.000 sampai +0.000 |
| held-out input sama (R02, N07, N09) | S2 | +0.049 | +0.000 sampai +0.100 | 0.0520 | +0.000 | -0.032 sampai +0.032 |
| held-out input sama (R02, N07, N09) | S4 | +0.008 | +0.000 sampai +0.027 | 0.7352 | +0.000 | +0.000 sampai +0.000 |
| dev (S01-S03) | S2 | +0.455 | +0.340 sampai +0.570 | 0.0000 | +0.000 | +0.000 sampai +0.000 |
| dev (S01-S03) | S4 | +0.085 | +0.038 sampai +0.140 | 0.0000 | +0.000 | +0.000 sampai +0.000 |

## 3. Beban review dan penulisan otomatis (rep1)

| Himpunan | Run | Butir | AUTO_ACCEPT benar | AUTO_ACCEPT salah | REVIEW_NULL | REVIEW_RAGU | Lain |
|---|---|---|---|---|---|---|---|
| held-out | bge-m3 | 208 | 71 | 0 | 134 | 0 | 3 |
| held-out | MiniLM | 208 | 68 | 0 | 137 | 0 | 3 |
| held-out input sama (R02, N07, N09) | bge-m3 | 187 | 62 | 0 | 123 | 0 | 2 |
| held-out input sama (R02, N07, N09) | MiniLM | 187 | 61 | 0 | 124 | 0 | 2 |
| dev (S01-S03) | bge-m3 | 77 | 70 | 0 | 5 | 0 | 2 |
| dev (S01-S03) | MiniLM | 77 | 59 | 0 | 16 | 0 | 2 |

## 4. Latensi per run (detik, median antarpengulangan)

| Run | bge-m3 | MiniLM |
|---|---|---|
| atribut/N07 | 417.8 | 425.2 |
| atribut/N09 | 534.0 | 534.5 |
| atribut/R01 | - | 104.7 |
| atribut/R02 | 330.0 | 329.8 |
| atribut_n08var/N08 | 153.1 | 179.0 |
| kombinasi/S01 | 111.1 | 542.6 |
| kombinasi/S02 | 168.9 | 490.7 |
| kombinasi/S03 | 186.7 | 599.7 |

Butir yang jawabannya berubah (S4, rep1): 14 (rincian `butir_berubah_S4.csv`).
