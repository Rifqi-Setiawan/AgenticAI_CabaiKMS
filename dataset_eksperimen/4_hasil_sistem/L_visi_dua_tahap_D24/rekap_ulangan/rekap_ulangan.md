# Ulangan run foto D24 (visi dua tahap): 3 ulangan

Input, registri, deskripsi varietas, kanonik, dan varietas DB sama di semua ulangan; skrip skor sama. Kolom D23 = satu run 7 Nov (nama berkas di prompt). Rerata dan SB dihitung antar ulangan (variasi model, bukan ketidakpastian sampel).

## Nama file berpasangan (PVT kartu tertutup, 40 foto x 3 nama)

| Metrik | Ulangan 1 | Ulangan 2 | Ulangan 3 | Rerata | SB | Rentang | D23 |
|---|---|---|---|---|---|---|---|
| PVT nama salah: ikut nama berkas (dari 40) | 2 | 2 | 2 | 2,00 | 0,00 | 2-2 | 30 |
| PVT nama salah: tindakan sesuai gold / REVIEW_MISMATCH benar (dari 40) | 7 | 7 | 7 | 7,00 | 0,00 | 7-7 | 0 |
| PVT nama salah: AUTO_LINK salah | 2 | 2 | 2 | 2,00 | 0,00 | 2-2 | 12 |
| PVT berpasangan: tindakan sesuai gold (dari 120) | 33 | 32 | 32 | 32,33 | 0,58 | 32-33 | 48 |
| PVT berpasangan: AUTO_LINK salah (dari 120) | 8 | 7 | 8 | 7,67 | 0,58 | 7-8 | 17 |
| PVT KNOWN NETRAL: status benar (dari 19) | 4 | 4 | 3 | 3,67 | 0,58 | 3-4 | 4 |
| PVT KNOWN NETRAL: tindakan sesuai gold | 16 | 15 | 15 | 15,33 | 0,58 | 15-16 | 16 |
| PVT KNOWN BENAR: status benar (dari 19) | 3 | 3 | 3 | 3,00 | 0,00 | 3-3 | 16 |
| PVT KNOWN BENAR: tindakan sesuai gold | 4 | 4 | 4 | 4,00 | 0,00 | 4-4 | 12 |
| PVT OTHER BENAR: status benar (dari 21) | 0 | 0 | 0 | 0,00 | 0,00 | 0-0 | 19 |
| PVT OTHER BENAR: tindakan sesuai gold | 3 | 3 | 3 | 3,00 | 0,00 | 3-3 | 17 |

## Foto dan workbook gabungan

| Metrik | Ulangan 1 | Ulangan 2 | Ulangan 3 | Rerata | SB | Rentang | D23 |
|---|---|---|---|---|---|---|---|
| Commons: status benar (dari 35) | 32 | 34 | 32 | 32,67 | 1,15 | 32-34 | 35 |
| Commons: Top-1 KNOWN | 0,714 | 1,000 | 0,714 | 0,810 | 0,165 | 0,714-1,000 | 1,000 |
| Commons: macro-F1 kelas gold | 0,867 | 0,958 | 0,876 | 0,900 | 0,050 | 0,867-0,958 | 1,000 |
| Commons: AUTO_LINK benar / total | 5/6 | 7/8 | 5/6 | - | - | - | 7/7 |
| Commons: AUTO_LINK salah | 1 | 1 | 1 | 1,00 | 0,00 | 1-1 | 0 |
| Indonesia S01-S03: status benar (dari 18) | 13 | 13 | 13 | 13,00 | 0,00 | 13-13 | 15 |
| Indonesia S01-S03: Top-1 KNOWN | 0,750 | 0,750 | 0,750 | 0,750 | 0,000 | 0,750-0,750 | 0,812 |
| Indonesia S01-S03: macro-F1 kelas gold | 0,633 | 0,633 | 0,633 | 0,633 | 0,000 | 0,633-0,633 | 0,734 |
| Indonesia S01-S03: AUTO_LINK benar / total | 12/13 | 12/13 | 12/13 | - | - | - | 12/12 |
| Indonesia S01-S03: AUTO_LINK salah | 1 | 1 | 1 | 1,00 | 0,00 | 1-1 | 0 |
| PVT kartu terlihat: status benar (dari 40) | 25 | 26 | 23 | 24,67 | 1,53 | 23-26 | 27 |
| PVT kartu terlihat: Top-1 KNOWN | 0,579 | 0,632 | 0,526 | 0,579 | 0,053 | 0,526-0,632 | 0,632 |
| PVT kartu terlihat: macro-F1 kelas gold | 0,806 | 0,821 | 0,771 | 0,799 | 0,025 | 0,771-0,821 | 0,864 |
| PVT kartu terlihat: AUTO_LINK benar / total | 8/13 | 9/13 | 7/11 | - | - | - | 12/19 |
| PVT kartu terlihat: AUTO_LINK salah | 5 | 4 | 4 | 4,33 | 0,58 | 4-5 | 7 |
| PVT kartu tertutup: status benar (dari 40) | 3 | 3 | 4 | 3,33 | 0,58 | 3-4 | 4 |
| PVT kartu tertutup: Top-1 KNOWN | 0,158 | 0,158 | 0,211 | 0,175 | 0,030 | 0,158-0,211 | 0,211 |
| PVT kartu tertutup: macro-F1 kelas gold | 0,259 | 0,269 | 0,259 | 0,263 | 0,006 | 0,259-0,269 | 0,276 |
| PVT kartu tertutup: AUTO_LINK benar / total | 2/6 | 1/4 | 4/7 | - | - | - | 3/8 |
| PVT kartu tertutup: AUTO_LINK salah | 4 | 3 | 3 | 3,33 | 0,58 | 3-4 | 5 |
| Workbook gabungan Indonesia F1 | 0,980 | 0,980 | 0,980 | 0,980 | 0,000 | 0,980-0,980 | 0,960 |
| Workbook P01+PVT terlihat F1 | 0,947 | 0,949 | 0,947 | 0,947 | 0,001 | 0,947-0,949 | 0,950 |
| Workbook P01+PVT tertutup F1 | 0,940 | 0,940 | 0,944 | 0,941 | 0,002 | 0,940-0,944 | 0,940 |

## Kestabilan jawaban per foto

- Foto ulang (Commons, Indonesia, PVT 2 kondisi): status, varietas, dan tindakan sama di semua ulangan pada 112/133 keputusan (84,2%).
- Nama file berpasangan: sama di semua ulangan pada 136/156 keputusan (87,2%).
