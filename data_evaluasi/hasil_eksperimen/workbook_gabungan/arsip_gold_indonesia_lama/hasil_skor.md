# Skor workbook akhir gabungan (sel atribut + link foto)

Satuan: unit tulisan (satu sel atribut atau satu link foto). Kolom: benar/salah tulis/terlewat | precision / recall / F1. Link foto benar = foto gold KNOWN di kolom varietas dan baris bagian tanaman yang benar. Definisi lengkap: docstring skrip.

| Run | Atribut b/s/t | P / R / F1 | Foto b/s/t | P / R / F1 | Gabungan b/s/t | P / R / F1 |
|---|---|---|---|---|---|---|
| Indonesia S01 | 74/0/4 | 1.000 / 0.949 / 0.974 | 5/2/1 | 0.714 / 0.833 / 0.769 | 79/2/5 | 0.975 / 0.940 / 0.958 |
| Indonesia S02 | 66/0/0 | 1.000 / 1.000 / 1.000 | 5/1/1 | 0.833 / 0.833 / 0.833 | 71/1/1 | 0.986 / 0.986 / 0.986 |
| Indonesia S03 | 72/0/40 | 1.000 / 0.643 / 0.783 | 4/3/2 | 0.571 / 0.667 / 0.615 | 76/3/42 | 0.962 / 0.644 / 0.772 |
| Commons F1 | - | - | 7/6/6 | 0.538 / 0.538 / 0.538 | 7/6/6 | 0.538 / 0.538 / 0.538 |
| Commons F2 | - | - | 9/3/4 | 0.750 / 0.692 / 0.720 | 9/3/4 | 0.750 / 0.692 / 0.720 |
| Commons F3 | - | - | 7/2/6 | 0.778 / 0.538 / 0.636 | 7/2/6 | 0.778 / 0.538 / 0.636 |
| Commons F4 | - | - | 10/3/2 | 0.769 / 0.833 / 0.800 | 10/3/2 | 0.769 / 0.833 / 0.800 |
| Commons F5 | - | - | 8/1/4 | 0.889 / 0.667 / 0.762 | 8/1/4 | 0.889 / 0.667 / 0.762 |
| Commons F6 | - | - | 8/4/4 | 0.667 / 0.667 / 0.667 | 8/4/4 | 0.667 / 0.667 / 0.667 |
| Commons F7 | - | - | 4/5/8 | 0.444 / 0.333 / 0.381 | 4/5/8 | 0.444 / 0.333 / 0.381 |
| Commons F8 | - | - | 10/0/2 | 1.000 / 0.833 / 0.909 | 10/0/2 | 1.000 / 0.833 / 0.909 |
|  |  |  |  |  |  |  |
| **Indonesia S01-S03** | 212/0/44 | 1.000 / 0.828 / 0.906 | 14/6/4 | 0.700 / 0.778 / 0.737 | 226/6/48 | 0.974 / 0.825 / 0.893 |
| **Commons F1-F8** | - | - | 63/24/36 | 0.724 / 0.636 / 0.677 | 63/24/36 | 0.724 / 0.636 / 0.677 |
| **SEMUA RUN** | 212/0/44 | 1.000 / 0.828 / 0.906 | 77/30/40 | 0.720 / 0.658 / 0.687 | 289/30/84 | 0.906 / 0.775 / 0.835 |

Rincian link foto: benar 77, salah: bagian tanaman 1, salah: foto OTHER 12, salah: foto UNCERTAIN 9, salah: varietas 8, tidak dinilai 4
