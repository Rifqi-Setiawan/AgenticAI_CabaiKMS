# Desain nama file berpasangan (D23): foto sama, nama berkas berbeda

PVT: 40 foto kartu tertutup, registri 24 varietas P01 + deskripsi morfologi P01 (D20). Indonesia: 6 foto x spreadsheet S01-S03 (registri dan deskripsi dari sheet kanonik run bge-m3). Jalur visi = vision_hook tanpa tulis KMS.

## 1. Per sel

| Set | Status gold | Varian nama file | Foto | Gagal | Tindakan sesuai gold | Status visual benar | AUTO_LINK salah | Ikut nama file | Sebaran tindakan |
|---|---|---|---|---|---|---|---|---|---|
| ind6 | KNOWN | NETRAL | 16 | 0 | 11/16 | 11/16 | 2/16 | - | AUTO_LINK 13, CANDIDATE 3 |
| ind6 | KNOWN | BENAR | 16 | 0 | 12/16 | 13/16 | 0/16 | - | AUTO_LINK 12, CANDIDATE 3, REVIEW_UNCERTAIN 1 |
| ind6 | OTHER | NETRAL | 2 | 0 | 1/2 | 1/2 | 0/2 | - | CANDIDATE 1, REVIEW_UNCERTAIN 1 |
| ind6 | OTHER | BENAR | 2 | 0 | 2/2 | 2/2 | 0/2 | - | CANDIDATE 2 |
| pvt40 | KNOWN | NETRAL | 19 | 0 | 16/19 | 4/19 | 3/19 | - | AUTO_LINK 6, REVIEW_UNCERTAIN 13 |
| pvt40 | KNOWN | BENAR | 19 | 0 | 12/19 | 16/19 | 0/19 | - | AUTO_LINK 11, REVIEW_UNCERTAIN 8 |
| pvt40 | KNOWN | SALAH_TERDAFTAR | 19 | 0 | 0/19 | 1/19 | 7/19 | 16/19 | AUTO_LINK 8, REVIEW_UNCERTAIN 11 |
| pvt40 | OTHER | NETRAL | 21 | 0 | 3/21 | 0/21 | 2/21 | - | AUTO_LINK 2, REVIEW_UNCERTAIN 19 |
| pvt40 | OTHER | BENAR | 21 | 0 | 17/21 | 19/21 | 0/21 | - | CANDIDATE 18, REVIEW_UNCERTAIN 3 |
| pvt40 | OTHER | SALAH_TERDAFTAR | 21 | 0 | 0/21 | 0/21 | 5/21 | 14/21 | AUTO_LINK 5, REVIEW_UNCERTAIN 16 |

## 2. Uji berpasangan (foto yang sama; selisih proporsi tindakan sesuai gold, bootstrap per foto)

| Set | Status gold | Perbandingan | Foto berpasangan | Selisih | CI 95% |
|---|---|---|---|---|---|
| pvt40 | KNOWN | BENAR vs NETRAL | 19 | -0.211 | -0.526 sampai +0.105 |
| pvt40 | KNOWN | SALAH_TERDAFTAR vs NETRAL | 19 | -0.842 | -1.000 sampai -0.684 |
| pvt40 | KNOWN | SALAH_TERDAFTAR vs BENAR | 19 | -0.632 | -0.842 sampai -0.421 |
| pvt40 | OTHER | BENAR vs NETRAL | 21 | +0.667 | +0.381 sampai +0.905 |
| pvt40 | OTHER | SALAH_TERDAFTAR vs NETRAL | 21 | -0.143 | -0.286 sampai +0.000 |
| pvt40 | OTHER | SALAH_TERDAFTAR vs BENAR | 21 | -0.810 | -0.952 sampai -0.619 |
| ind6 | KNOWN | BENAR vs NETRAL | 16 | +0.062 | -0.250 sampai +0.375 |
| ind6 | OTHER | BENAR vs NETRAL | 2 | +0.500 | +0.000 sampai +1.000 |

Total PVT: tindakan sesuai gold 48/120, AUTO_LINK salah 17/120.
Catatan: gold bagian tanaman PVT masih usulan AI; hanya memengaruhi foto berbagian tanpa baris Gambar (D21).