# Skor workbook akhir gabungan (sel atribut + link foto)

Satuan: unit tulisan (satu sel atribut atau satu link foto). Kolom: benar/salah tulis/terlewat | precision / recall / F1. Link foto benar = foto gold KNOWN di kolom varietas dan baris bagian tanaman yang benar. Definisi lengkap: docstring skrip.

| Run | Atribut b/s/t | P / R / F1 | Foto b/s/t | P / R / F1 | Gabungan b/s/t | P / R / F1 |
|---|---|---|---|---|---|---|
| Indonesia S01 | 74/0/4 | 1.000 / 0.949 / 0.974 | 4/4/4 | 0.500 / 0.500 / 0.500 | 78/4/8 | 0.951 / 0.907 / 0.929 |
| Indonesia S02 | 66/0/0 | 1.000 / 1.000 / 1.000 | 5/3/3 | 0.625 / 0.625 / 0.625 | 71/3/3 | 0.959 / 0.959 / 0.959 |
| Indonesia S03 | 72/0/40 | 1.000 / 0.643 / 0.783 | 3/5/3 | 0.375 / 0.500 / 0.429 | 75/5/43 | 0.938 / 0.636 / 0.758 |
| Commons F1 | - | - | 7/6/6 | 0.538 / 0.538 / 0.538 | 7/6/6 | 0.538 / 0.538 / 0.538 |
| Commons F2 | - | - | 9/3/4 | 0.750 / 0.692 / 0.720 | 9/3/4 | 0.750 / 0.692 / 0.720 |
| Commons F3 | - | - | 7/2/6 | 0.778 / 0.538 / 0.636 | 7/2/6 | 0.778 / 0.538 / 0.636 |
| Commons F4 | - | - | 10/3/2 | 0.769 / 0.833 / 0.800 | 10/3/2 | 0.769 / 0.833 / 0.800 |
| Commons F5 | - | - | 8/1/4 | 0.889 / 0.667 / 0.762 | 8/1/4 | 0.889 / 0.667 / 0.762 |
| Commons F6 | - | - | 8/4/4 | 0.667 / 0.667 / 0.667 | 8/4/4 | 0.667 / 0.667 / 0.667 |
| Commons F7 | - | - | 4/5/8 | 0.444 / 0.333 / 0.381 | 4/5/8 | 0.444 / 0.333 / 0.381 |
| Commons F8 | - | - | 10/0/2 | 1.000 / 0.833 / 0.909 | 10/0/2 | 1.000 / 0.833 / 0.909 |
|  |  |  |  |  |  |  |
| **Indonesia S01-S03** | 212/0/44 | 1.000 / 0.828 / 0.906 | 12/12/10 | 0.500 / 0.545 / 0.522 | 224/12/54 | 0.949 / 0.806 / 0.872 |
| **Commons F1-F8** | - | - | 63/24/36 | 0.724 / 0.636 / 0.677 | 63/24/36 | 0.724 / 0.636 / 0.677 |
| **SEMUA RUN** | 212/0/44 | 1.000 / 0.828 / 0.906 | 75/36/46 | 0.676 / 0.620 / 0.647 | 287/36/90 | 0.889 / 0.761 / 0.820 |

Rincian link foto: benar 75, salah: bagian tanaman 4, salah: foto OTHER 18, salah: foto UNCERTAIN 4, salah: varietas 10
