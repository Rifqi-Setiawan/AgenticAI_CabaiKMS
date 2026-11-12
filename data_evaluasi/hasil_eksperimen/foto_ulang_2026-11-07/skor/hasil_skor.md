# Run ulang foto dan workbook gabungan (7 Nov 2026)

Data bersih D19, kode visi D20 (deskripsi varietas dari sheet kanonik run), embedding bge-m3 (D22). Jalur visi = vision_hook tanpa tulis KMS (uji_visi_commons_vps.py). Definisi metrik: docstring skrip/skor_foto_ulang.py.

## 1. Klasifikasi foto

| Set | Foto dinilai | Gagal | Status benar | Macro-F1 kelas gold (CI 95%) | Macro-F1 3 kelas | Top-1 KNOWN (CI 95%) | Recall OTHER | Non-KNOWN dipaksa KNOWN | AUTO_LINK benar | Bagian benar | Tindakan fusi sesuai gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| commons35 | 35 | 0 | 35/35 | 1.000 (1.000-1.000) | 0.667 | 1.000 (1.000-1.000) | 28/28 = 1.000 | 0/28 = 0.000 | 7/7 = 1.000 | 31/32 = 0.969 | 35/35 = 1.000 |
| S01 | 6 | 0 | 5/6 | 0.909 (0.667-1.000) | 0.303 | 0.833 (0.500-1.000) | 0/0 | 0/0 | 4/4 = 1.000 | 5/6 = 0.833 | - |
| S02 | 6 | 0 | 5/6 | 0.909 (0.667-1.000) | 0.303 | 0.833 (0.500-1.000) | 0/0 | 0/0 | 5/5 = 1.000 | 5/6 = 0.833 | - |
| S03 | 6 | 0 | 5/6 | 0.829 (0.400-1.000) | 0.552 | 0.750 (0.250-1.000) | 2/2 = 1.000 | 0/2 = 0.000 | 3/3 = 1.000 | 5/6 = 0.833 | - |
| pvt40_terlihat | 40 | 0 | 27/40 | 0.864 (0.755-0.949) | 0.576 | 0.632 (0.412-0.846) | 15/21 = 0.714 | 2/21 = 0.095 | 12/19 = 0.632 | 36/36 = 1.000 | 30/40 = 0.750 |
| pvt40_tertutup | 40 | 0 | 4/40 | 0.276 (0.150-0.371) | 0.184 | 0.211 (0.050-0.417) | 0/21 = 0.000 | 2/21 = 0.095 | 3/8 = 0.375 | 35/36 = 0.972 | 11/40 = 0.275 |
| indonesia_S01-S03 | 18 | 0 | 15/18 | 0.734 (0.419-1.000) | 0.489 | 0.812 (0.600-1.000) | 2/2 = 1.000 | 0/2 = 0.000 | 12/12 = 1.000 | 15/18 = 0.833 | - |

Tindakan fusi per set: commons35: {'AUTO_LINK': 7, 'CANDIDATE': 27, 'REVIEW_MISMATCH': 1}; S01: {'AUTO_LINK': 4, 'CANDIDATE': 1, 'REVIEW_UNCERTAIN': 1}; S02: {'AUTO_LINK': 5, 'CANDIDATE': 1}; S03: {'AUTO_LINK': 3, 'CANDIDATE': 3}; pvt40_terlihat: {'AUTO_LINK': 19, 'CANDIDATE': 15, 'REVIEW_UNCERTAIN': 6}; pvt40_tertutup: {'AUTO_LINK': 8, 'REVIEW_UNCERTAIN': 32}; indonesia_S01-S03: {'AUTO_LINK': 12, 'CANDIDATE': 5, 'REVIEW_UNCERTAIN': 1}

AUTO_LINK benar per kondisi nama file (Commons): INFORMATIF 3/3 = 1.000, MENYESATKAN 0/0, NETRAL 4/4 = 1.000

## 2. Workbook gabungan (sel atribut + tautan foto)

| Run | Sel P / R / F1 | Tautan foto benar / salah / terlewat (harapan) | Gabungan P / R / F1 |
|---|---|---|---|
| S01 | 1.000 / 1.000 / 1.000 | 3 / 1 / 3 (6) | 0.977 / 0.935 / 0.956 |
| S02 | 1.000 / 1.000 / 1.000 | 4 / 1 / 2 (6) | 0.980 / 0.960 / 0.970 |
| S03 | 1.000 / 1.000 / 1.000 | 2 / 1 / 2 (4) | 0.968 / 0.938 / 0.952 |
| P01+pvt40_terlihat | 1.000 / 0.930 / 0.964 | 12 / 7 / 6 (18) | 0.982 / 0.919 / 0.950 |
| P01+pvt40_tertutup | 1.000 / 0.930 / 0.964 | 3 / 5 / 15 (18) | 0.987 / 0.898 / 0.940 |
| Indonesia S01-S03 total | | | 0.976 / 0.945 / 0.960 |

Catatan: gold atribut dan kunci sel P01 belum diverifikasi. Commons hanya punya 7 foto KNOWN (registri 1 varietas).