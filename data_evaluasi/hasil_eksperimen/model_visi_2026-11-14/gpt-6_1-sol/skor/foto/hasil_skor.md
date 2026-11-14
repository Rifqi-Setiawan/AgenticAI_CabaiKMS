# Run ulang foto dan workbook gabungan (7 Nov 2026)

Data bersih D19, kode visi D20 (deskripsi varietas dari sheet kanonik run), embedding bge-m3 (D22). Jalur visi = vision_hook tanpa tulis KMS (uji_visi_commons_vps.py). Definisi metrik: docstring skrip/skor_foto_ulang.py.

## 1. Klasifikasi foto

| Set | Foto dinilai | Gagal | Status benar | Macro-F1 kelas gold (CI 95%) | Macro-F1 3 kelas | Top-1 KNOWN (CI 95%) | Recall OTHER | Non-KNOWN dipaksa KNOWN | AUTO_LINK benar | Bagian benar | Tindakan fusi sesuai gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| commons35 | 35 | 0 | 0/35 | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | 0/28 = 0.000 | 0/28 = 0.000 | 0/0 | 31/32 = 0.969 | 0/35 = 0.000 |
| S01 | 6 | 0 | 2/6 | 0.500 (0.000-0.800) | 0.167 | 0.333 (0.000-0.667) | 0/0 | 0/0 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| S02 | 6 | 0 | 2/6 | 0.500 (0.000-0.800) | 0.167 | 0.333 (0.000-0.667) | 0/0 | 0/0 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| S03 | 6 | 0 | 3/6 | 0.533 (0.143-0.900) | 0.356 | 0.500 (0.000-1.000) | 1/2 = 0.500 | 0/2 = 0.000 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| pvt40_terlihat | 40 | 0 | 0/40 | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | 0/21 = 0.000 | 0/21 = 0.000 | 0/0 | 33/36 = 0.917 | 4/40 = 0.100 |
| pvt40_tertutup | 40 | 0 | 0/40 | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | 0/21 = 0.000 | 0/21 = 0.000 | 0/0 | 32/36 = 0.889 | 4/40 = 0.100 |
| indonesia_S01-S03 | 18 | 0 | 7/18 | 0.398 (0.158-0.646) | 0.265 | 0.375 (0.133-0.625) | 1/2 = 0.500 | 0/2 = 0.000 | 3/3 = 1.000 | 18/18 = 1.000 | - |

Tindakan fusi per set: commons35: {'REVIEW_UNCERTAIN': 35}; S01: {'AUTO_LINK': 1, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 4}; S02: {'AUTO_LINK': 1, 'CANDIDATE': 1, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 3}; S03: {'AUTO_LINK': 1, 'CANDIDATE': 3, 'REVIEW_UNCERTAIN': 2}; pvt40_terlihat: {'REVIEW_UNCERTAIN': 40}; pvt40_tertutup: {'REVIEW_UNCERTAIN': 40}; indonesia_S01-S03: {'AUTO_LINK': 3, 'CANDIDATE': 4, 'REVIEW_MISMATCH': 2, 'REVIEW_UNCERTAIN': 9}

AUTO_LINK benar per kondisi nama file (Commons): INFORMATIF 0/0, MENYESATKAN 0/0, NETRAL 0/0

## 2. Workbook gabungan (sel atribut + tautan foto)

| Run | Sel P / R / F1 | Tautan foto benar / salah / terlewat (harapan) | Gabungan P / R / F1 |
|---|---|---|---|
| S01 | 1.000 / 1.000 / 1.000 | 1 / 0 / 5 (6) | 1.000 / 0.891 / 0.943 |
| S02 | 1.000 / 1.000 / 1.000 | 1 / 0 / 5 (6) | 1.000 / 0.900 / 0.947 |
| S03 | 1.000 / 1.000 / 1.000 | 1 / 0 / 3 (4) | 1.000 / 0.906 / 0.951 |
| P01+pvt40_terlihat | 1.000 / 0.930 / 0.964 | 0 / 0 / 18 (18) | 1.000 / 0.890 / 0.942 |
| P01+pvt40_tertutup | 1.000 / 0.930 / 0.964 | 0 / 0 / 18 (18) | 1.000 / 0.890 / 0.942 |
| Indonesia S01-S03 total | | | 1.000 / 0.898 / 0.947 |

Catatan: gold atribut dan kunci sel P01 terverifikasi. Commons hanya punya 7 foto KNOWN (registri 1 varietas).