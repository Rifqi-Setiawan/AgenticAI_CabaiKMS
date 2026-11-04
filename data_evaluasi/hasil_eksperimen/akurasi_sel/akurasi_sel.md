# Akurasi isi spreadsheet per sel (masukan dosen poin 3)

Kunci: gold pemetaan ONE_TO_ONE + nilai mentah sumber (pembaca terpisah dari parser produksi). Definisi metrik di docstring skrip/akurasi_sel.py. Keluaran paper = hasil UI 31 Okt 2026 (dataset_eksperimen/4_hasil_sistem).

## Per workbook (keluaran paper)

| Workbook | Split | Kolom varietas benar | Sel harapan | Ketat P / R / F1 | Posisi P / R / F1 | Normalisasi identik / berubah setara / berbeda |
|---|---|---|---|---|---|---|
| R01 | dev | 2/2 (kolom 2) | 2 | 0.000 / 0.000 / 0.000 | 0.000 / 0.000 / 0.000 | 0 / 0 / 2 |
| R02 | held-out | 0/6 (kolom 6) | 79 | 0.000 / 0.000 / 0.000 | 1.000 / 1.000 / 1.000 | 58 / 21 / 0 |
| N07 | held-out | 0/3 (kolom 3) | 37 | 0.000 / 0.000 / 0.000 | 1.000 / 0.973 / 0.986 | 30 / 6 / 0 |
| N08 | held-out | 17/17 (kolom 17) | 153 | 1.000 / 0.778 / 0.875 | 1.000 / 0.778 / 0.875 | 119 / 0 / 0 |
| N09 | held-out | 6/6 (kolom 6) | 73 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 58 / 15 / 0 |
| S01 | dev | 4/4 (kolom 4) | 78 | 1.000 / 0.949 / 0.974 | 1.000 / 0.949 / 0.974 | 47 / 27 / 0 |
| S02 | dev | 3/3 (kolom 3) | 66 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 | 56 / 10 / 0 |
| S03 | dev | 4/4 (kolom 4) | 112 | 1.000 / 0.643 / 0.783 | 1.000 / 0.643 / 0.783 | 40 / 32 / 0 |

## Gabungan (micro), CI 95% bootstrap per workbook

| Himpunan | Mode | Benar | Salah tulis | Terlewat | Precision [CI] | Recall [CI] | F1 [CI] |
|---|---|---|---|---|---|---|---|
| held-out | ketat | 192 | 116 | 150 | 0.623 [0.000, 1.000] | 0.561 [0.000, 0.855] | 0.591 [0.000, 0.919] |
| held-out | posisi | 307 | 0 | 35 | 1.000 [1.000, 1.000] | 0.898 [0.808, 1.000] | 0.946 [0.894, 1.000] |
| semua | ketat | 404 | 118 | 196 | 0.774 [0.409, 0.997] | 0.673 [0.376, 0.885] | 0.720 [0.391, 0.931] |
| semua | posisi | 519 | 2 | 81 | 0.996 [0.982, 1.000] | 0.865 [0.761, 0.987] | 0.926 [0.862, 0.992] |

## Rerun N07 dan R02 pada commit ac4f2e4 (perbaikan deteksi kolom varietas)

| Workbook | Kolom varietas benar | Ketat P / R / F1 | Posisi P / R / F1 |
|---|---|---|---|
| N07 | 3/3 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
| R02 | 6/6 | 1.000 / 1.000 / 1.000 | 1.000 / 1.000 / 1.000 |
