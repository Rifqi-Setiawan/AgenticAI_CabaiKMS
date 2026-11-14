# Desain nama file berpasangan (D23): foto sama, nama berkas berbeda

PVT: 40 foto kartu tertutup, registri 24 varietas P01 + deskripsi morfologi P01 (D20). Indonesia: 6 foto x spreadsheet S01-S03 (registri dan deskripsi dari sheet kanonik run bge-m3). Jalur visi = vision_hook tanpa tulis KMS.

## 1. Per sel

| Set | Status gold | Varian nama file | Foto | Gagal | Tindakan sesuai gold | Status visual benar | AUTO_LINK salah | Ikut nama file | Sebaran tindakan |
|---|---|---|---|---|---|---|---|---|---|
| ind6 | KNOWN | NETRAL | 16 | 0 | 15/16 | 13/16 | 0/16 | - | AUTO_LINK 13, CANDIDATE 1, REVIEW_UNCERTAIN 2 |
| ind6 | KNOWN | BENAR | 16 | 0 | 12/16 | 12/16 | 0/16 | - | AUTO_LINK 12, CANDIDATE 1, REVIEW_MISMATCH 2, REVIEW_UNCERTAIN 1 |
| ind6 | OTHER | NETRAL | 2 | 0 | 2/2 | 2/2 | 0/2 | - | CANDIDATE 2 |
| ind6 | OTHER | BENAR | 2 | 0 | 1/2 | 1/2 | 1/2 | - | AUTO_LINK 1, CANDIDATE 1 |
| pvt40 | KNOWN | NETRAL | 19 | 0 | 15/19 | 3/19 | 4/19 | - | AUTO_LINK 6, REVIEW_UNCERTAIN 13 |
| pvt40 | KNOWN | BENAR | 19 | 1 | 4/19 | 3/19 | 0/19 | - | AUTO_LINK 3, FAILED 1, REVIEW_MISMATCH 3, REVIEW_UNCERTAIN 12 |
| pvt40 | KNOWN | SALAH_TERDAFTAR | 19 | 0 | 6/19 | 3/19 | 2/19 | 2/19 | AUTO_LINK 2, REVIEW_MISMATCH 6, REVIEW_UNCERTAIN 11 |
| pvt40 | OTHER | NETRAL | 21 | 0 | 3/21 | 0/21 | 1/21 | - | AUTO_LINK 1, REVIEW_UNCERTAIN 20 |
| pvt40 | OTHER | BENAR | 21 | 0 | 3/21 | 0/21 | 1/21 | - | AUTO_LINK 1, REVIEW_UNCERTAIN 20 |
| pvt40 | OTHER | SALAH_TERDAFTAR | 21 | 0 | 1/21 | 0/21 | 0/21 | 0/21 | REVIEW_MISMATCH 1, REVIEW_UNCERTAIN 20 |

## 2. Uji berpasangan (foto yang sama; selisih proporsi tindakan sesuai gold, bootstrap per foto)

| Set | Status gold | Perbandingan | Foto berpasangan | Selisih | CI 95% |
|---|---|---|---|---|---|
| pvt40 | KNOWN | BENAR vs NETRAL | 19 | -0.579 | -0.842 sampai -0.263 |
| pvt40 | KNOWN | SALAH_TERDAFTAR vs NETRAL | 19 | -0.474 | -0.789 sampai -0.105 |
| pvt40 | KNOWN | SALAH_TERDAFTAR vs BENAR | 19 | +0.105 | -0.158 sampai +0.368 |
| pvt40 | OTHER | BENAR vs NETRAL | 21 | +0.000 | +0.000 sampai +0.000 |
| pvt40 | OTHER | SALAH_TERDAFTAR vs NETRAL | 21 | -0.095 | -0.286 sampai +0.095 |
| pvt40 | OTHER | SALAH_TERDAFTAR vs BENAR | 21 | -0.095 | -0.286 sampai +0.095 |
| ind6 | KNOWN | BENAR vs NETRAL | 16 | -0.188 | -0.438 sampai +0.062 |
| ind6 | OTHER | BENAR vs NETRAL | 2 | -0.500 | -1.000 sampai +0.000 |

Total PVT: tindakan sesuai gold 32/120, AUTO_LINK salah 8/120.
Catatan: bagian tanaman hanya memengaruhi foto berbagian tanpa baris Gambar (D21).