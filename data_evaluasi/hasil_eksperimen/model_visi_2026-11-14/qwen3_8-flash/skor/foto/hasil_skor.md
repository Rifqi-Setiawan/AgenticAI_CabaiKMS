# Run ulang foto dan workbook gabungan (7 Nov 2026)

Data bersih D19, kode visi D20 (deskripsi varietas dari sheet kanonik run), embedding bge-m3 (D22). Jalur visi = vision_hook tanpa tulis KMS (uji_visi_commons_vps.py). Definisi metrik: docstring skrip/skor_foto_ulang.py.

## 1. Klasifikasi foto

| Set | Foto dinilai | Gagal | Status benar | Macro-F1 kelas gold (CI 95%) | Macro-F1 3 kelas | Top-1 KNOWN (CI 95%) | Recall OTHER | Non-KNOWN dipaksa KNOWN | AUTO_LINK benar | Bagian benar | Tindakan fusi sesuai gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| commons35 | 35 | 0 | 30/35 | 0.730 (0.464-0.921) | 0.487 | 0.429 (0.000-0.833) | 27/28 = 0.964 | 1/28 = 0.036 | 3/3 = 1.000 | 31/32 = 0.969 | 30/35 = 0.857 |
| S01 | 6 | 0 | 0/6 | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | 0/0 | 0/0 | 0/0 | 6/6 = 1.000 | - |
| S02 | 6 | 0 | 1/6 | 0.286 (0.000-0.667) | 0.095 | 0.167 (0.000-0.500) | 0/0 | 0/0 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| S03 | 6 | 0 | 3/6 | 0.486 (0.143-0.829) | 0.324 | 0.250 (0.000-0.750) | 2/2 = 1.000 | 0/2 = 0.000 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| pvt40_terlihat | 40 | 0 | 25/40 | 0.663 (0.501-0.804) | 0.442 | 0.526 (0.294-0.750) | 15/21 = 0.714 | 2/21 = 0.095 | 10/11 = 0.909 | 28/36 = 0.778 | 23/40 = 0.575 |
| pvt40_tertutup | 40 | 0 | 8/40 | 0.406 (0.226-0.566) | 0.271 | 0.053 (0.000-0.176) | 7/21 = 0.333 | 1/21 = 0.048 | 1/6 = 0.167 | 30/36 = 0.833 | 12/40 = 0.300 |
| indonesia_S01-S03 | 18 | 0 | 4/18 | 0.222 (0.053-0.416) | 0.148 | 0.125 (0.000-0.312) | 2/2 = 1.000 | 0/2 = 0.000 | 2/2 = 1.000 | 18/18 = 1.000 | - |

Tindakan fusi per set: commons35: {'AUTO_LINK': 3, 'CANDIDATE': 28, 'REVIEW_MISMATCH': 3, 'REVIEW_UNCERTAIN': 1}; S01: {'CANDIDATE': 3, 'REVIEW_MISMATCH': 2, 'REVIEW_UNCERTAIN': 1}; S02: {'AUTO_LINK': 1, 'CANDIDATE': 3, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 1}; S03: {'AUTO_LINK': 1, 'CANDIDATE': 5}; pvt40_terlihat: {'AUTO_LINK': 11, 'CANDIDATE': 14, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 14}; pvt40_tertutup: {'AUTO_LINK': 6, 'CANDIDATE': 8, 'REVIEW_UNCERTAIN': 26}; indonesia_S01-S03: {'AUTO_LINK': 2, 'CANDIDATE': 11, 'REVIEW_MISMATCH': 3, 'REVIEW_UNCERTAIN': 2}

AUTO_LINK benar per kondisi nama file (Commons): INFORMATIF 1/1 = 1.000, MENYESATKAN 0/0, NETRAL 2/2 = 1.000

## 2. Workbook gabungan (sel atribut + tautan foto)

| Run | Sel P / R / F1 | Tautan foto benar / salah / terlewat (harapan) | Gabungan P / R / F1 |
|---|---|---|---|
| S01 | 1.000 / 1.000 / 1.000 | 0 / 0 / 6 (6) | 1.000 / 0.870 / 0.930 |
| S02 | 1.000 / 1.000 / 1.000 | 1 / 0 / 5 (6) | 1.000 / 0.900 / 0.947 |
| S03 | 1.000 / 1.000 / 1.000 | 1 / 0 / 3 (4) | 1.000 / 0.906 / 0.951 |
| P01+pvt40_terlihat | 1.000 / 0.930 / 0.964 | 8 / 3 / 10 (18) | 0.992 / 0.910 / 0.949 |
| P01+pvt40_tertutup | 1.000 / 0.930 / 0.964 | 1 / 5 / 17 (18) | 0.987 / 0.893 / 0.938 |
| Indonesia S01-S03 total | | | 1.000 / 0.891 / 0.942 |

Catatan: gold atribut dan kunci sel P01 terverifikasi. Commons hanya punya 7 foto KNOWN (registri 1 varietas).