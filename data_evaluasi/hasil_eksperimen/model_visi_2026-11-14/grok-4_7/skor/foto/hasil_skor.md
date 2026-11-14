# Run ulang foto dan workbook gabungan (7 Nov 2026)

Data bersih D19, kode visi D20 (deskripsi varietas dari sheet kanonik run), embedding bge-m3 (D22). Jalur visi = vision_hook tanpa tulis KMS (uji_visi_commons_vps.py). Definisi metrik: docstring skrip/skor_foto_ulang.py.

## 1. Klasifikasi foto

| Set | Foto dinilai | Gagal | Status benar | Macro-F1 kelas gold (CI 95%) | Macro-F1 3 kelas | Top-1 KNOWN (CI 95%) | Recall OTHER | Non-KNOWN dipaksa KNOWN | AUTO_LINK benar | Bagian benar | Tindakan fusi sesuai gold |
|---|---|---|---|---|---|---|---|---|---|---|---|
| commons35 | 35 | 0 | 28/35 | 0.607 (0.463-0.815) | 0.405 | 0.143 (0.000-0.500) | 27/28 = 0.964 | 0/28 = 0.000 | 0/0 | 31/32 = 0.969 | 16/35 = 0.457 |
| S01 | 6 | 0 | 2/6 | 0.667 (0.286-0.909) | 0.222 | 0.333 (0.000-0.667) | 0/0 | 0/0 | 1/1 = 1.000 | 6/6 = 1.000 | - |
| S02 | 6 | 0 | 2/6 | 0.667 (0.286-0.909) | 0.222 | 0.333 (0.000-0.667) | 0/0 | 0/0 | 2/2 = 1.000 | 5/6 = 0.833 | - |
| S03 | 6 | 0 | 2/6 | 0.450 (0.000-0.833) | 0.300 | 0.250 (0.000-0.750) | 1/2 = 0.500 | 0/2 = 0.000 | 0/0 | 6/6 = 1.000 | - |
| pvt40_terlihat | 40 | 0 | 6/40 | 0.333 (0.147-0.494) | 0.222 | 0.158 (0.000-0.348) | 3/21 = 0.143 | 0/21 = 0.000 | 0/0 | 29/36 = 0.806 | 4/40 = 0.100 |
| pvt40_tertutup | 40 | 0 | 0/40 | 0.087 (0.000-0.188) | 0.058 | 0.000 (0.000-0.000) | 0/21 = 0.000 | 2/21 = 0.095 | 0/0 | 31/36 = 0.861 | 4/40 = 0.100 |
| indonesia_S01-S03 | 18 | 0 | 6/18 | 0.471 (0.211-0.733) | 0.314 | 0.312 (0.118-0.562) | 1/2 = 0.500 | 0/2 = 0.000 | 3/3 = 1.000 | 17/18 = 0.944 | - |

Tindakan fusi per set: commons35: {'CANDIDATE': 16, 'REVIEW_UNCERTAIN': 19}; S01: {'AUTO_LINK': 1, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 4}; S02: {'AUTO_LINK': 2, 'REVIEW_UNCERTAIN': 4}; S03: {'CANDIDATE': 1, 'REVIEW_UNCERTAIN': 5}; pvt40_terlihat: {'REVIEW_UNCERTAIN': 40}; pvt40_tertutup: {'REVIEW_UNCERTAIN': 40}; indonesia_S01-S03: {'AUTO_LINK': 3, 'CANDIDATE': 1, 'REVIEW_MISMATCH': 1, 'REVIEW_UNCERTAIN': 13}

AUTO_LINK benar per kondisi nama file (Commons): INFORMATIF 0/0, MENYESATKAN 0/0, NETRAL 0/0

## 2. Workbook gabungan (sel atribut + tautan foto)

| Run | Sel P / R / F1 | Tautan foto benar / salah / terlewat (harapan) | Gabungan P / R / F1 |
|---|---|---|---|
| S01 | 1.000 / 1.000 / 1.000 | 1 / 0 / 5 (6) | 1.000 / 0.891 / 0.943 |
| S02 | 1.000 / 1.000 / 1.000 | 2 / 0 / 4 (6) | 1.000 / 0.920 / 0.958 |
| S03 | 1.000 / 1.000 / 1.000 | 0 / 0 / 4 (4) | 1.000 / 0.875 / 0.933 |
| P01+pvt40_terlihat | 1.000 / 0.930 / 0.964 | 0 / 0 / 18 (18) | 1.000 / 0.890 / 0.942 |
| P01+pvt40_tertutup | 1.000 / 0.930 / 0.964 | 0 / 0 / 18 (18) | 1.000 / 0.890 / 0.942 |
| Indonesia S01-S03 total | | | 1.000 / 0.898 / 0.947 |

Catatan: gold atribut dan kunci sel P01 terverifikasi. Commons hanya punya 7 foto KNOWN (registri 1 varietas).