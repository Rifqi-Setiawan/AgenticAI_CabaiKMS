# Perbandingan model visi (D26)

Harness, input, registri, deskripsi varietas, kanonik, varietas DB, mode two_stage, dan skrip skor sama; yang berbeda hanya model visi (`CABAI_KMS_EVAL_VISION_MODEL`). Model teks tetap Gemini 3.8 Flash medium.

| Metrik | Gemini 3.8 Flash high (rerata 3 ulangan) | Gemini 3.8 Flash high rentang | Claude Opus 5.5 | GPT-6 Astra | GPT-6.1 Sol | Qwen3.8 Flash | Grok 4.7 |
|---|---|---|---|---|---|---|---|
| PVT nama salah: ikut nama berkas (dari 40) | 2,00 | 2-2 | 1,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| PVT nama salah: tindakan sesuai gold / REVIEW_MISMATCH benar (dari 40) | 7,00 | 7-7 | 1,00 | 0,00 | 0,00 | 17,00 | 2,00 |
| PVT nama salah: AUTO_LINK salah | 2,00 | 2-2 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| PVT berpasangan: tindakan sesuai gold (dari 120) | 32,33 | 32-33 | 27,00 | 26,00 | 26,00 | 43,00 | 28,00 |
| PVT berpasangan: AUTO_LINK salah (dari 120) | 7,67 | 7-8 | 0,00 | 0,00 | 0,00 | 8,00 | 0,00 |
| PVT KNOWN NETRAL: status benar (dari 19) | 3,67 | 3-4 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| PVT KNOWN NETRAL: tindakan sesuai gold | 15,33 | 15-16 | 19,00 | 19,00 | 19,00 | 9,00 | 19,00 |
| PVT KNOWN BENAR: status benar (dari 19) | 3,00 | 3-3 | 0,00 | 0,00 | 0,00 | 2,00 | 0,00 |
| PVT KNOWN BENAR: tindakan sesuai gold | 4,00 | 4-4 | 1,00 | 1,00 | 1,00 | 3,00 | 1,00 |
| PVT OTHER BENAR: status benar (dari 21) | 0,00 | 0-0 | 0,00 | 0,00 | 0,00 | 5,00 | 0,00 |
| PVT OTHER BENAR: tindakan sesuai gold | 3,00 | 3-3 | 3,00 | 3,00 | 3,00 | 6,00 | 3,00 |
| Commons: status benar (dari 35) | 32,67 | 32-34 | 28,00 | 0,00 | 0,00 | 30,00 | 28,00 |
| Commons: Top-1 KNOWN | 0,810 | 0,714-1,000 | 0,143 | 0,000 | 0,000 | 0,429 | 0,143 |
| Commons: macro-F1 kelas gold | 0,900 | 0,867-0,958 | 0,607 | 0,000 | 0,000 | 0,730 | 0,607 |
| Commons: AUTO_LINK benar / total | 5/6, 7/8, 5/6 | - | 0/0 | 0/0 | 0/0 | 3/3 | 0/0 |
| Commons: AUTO_LINK salah | 1,00 | 1-1 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| Indonesia S01-S03: status benar (dari 18) | 13,00 | 13-13 | 8,00 | 6,00 | 7,00 | 4,00 | 6,00 |
| Indonesia S01-S03: Top-1 KNOWN | 0,750 | 0,750-0,750 | 0,375 | 0,312 | 0,375 | 0,125 | 0,312 |
| Indonesia S01-S03: macro-F1 kelas gold | 0,633 | 0,633-0,633 | 0,554 | 0,381 | 0,398 | 0,222 | 0,471 |
| Indonesia S01-S03: AUTO_LINK benar / total | 12/13 | - | 0/0 | 1/1 | 3/3 | 2/2 | 3/3 |
| Indonesia S01-S03: AUTO_LINK salah | 1,00 | 1-1 | 0,00 | 0,00 | 0,00 | 0,00 | 0,00 |
| PVT kartu terlihat: status benar (dari 40) | 24,67 | 23-26 | 3,00 | 0,00 | 0,00 | 25,00 | 6,00 |
| PVT kartu terlihat: Top-1 KNOWN | 0,579 | 0,526-0,632 | 0,158 | 0,000 | 0,000 | 0,526 | 0,158 |
| PVT kartu terlihat: macro-F1 kelas gold | 0,799 | 0,771-0,821 | 0,208 | 0,000 | 0,000 | 0,663 | 0,333 |
| PVT kartu terlihat: AUTO_LINK benar / total | 8/13, 9/13, 7/11 | - | 0/0 | 0/0 | 0/0 | 10/11 | 0/0 |
| PVT kartu terlihat: AUTO_LINK salah | 4,33 | 4-5 | 0,00 | 0,00 | 0,00 | 1,00 | 0,00 |
| PVT kartu tertutup: status benar (dari 40) | 3,33 | 3-4 | 0,00 | 0,00 | 0,00 | 8,00 | 0,00 |
| PVT kartu tertutup: Top-1 KNOWN | 0,175 | 0,158-0,211 | 0,000 | 0,000 | 0,000 | 0,053 | 0,000 |
| PVT kartu tertutup: macro-F1 kelas gold | 0,263 | 0,259-0,269 | 0,095 | 0,000 | 0,000 | 0,406 | 0,087 |
| PVT kartu tertutup: AUTO_LINK benar / total | 2/6, 1/4, 4/7 | - | 0/0 | 0/0 | 0/0 | 1/6 | 0/0 |
| PVT kartu tertutup: AUTO_LINK salah | 3,33 | 3-4 | 0,00 | 0,00 | 0,00 | 5,00 | 0,00 |
| Workbook gabungan Indonesia F1 | 0,980 | 0,980-0,980 | 0,933 | 0,938 | 0,947 | 0,942 | 0,947 |
| Workbook P01+PVT terlihat F1 | 0,947 | 0,947-0,949 | 0,942 | 0,942 | 0,942 | 0,949 | 0,942 |
| Workbook P01+PVT tertutup F1 | 0,941 | 0,940-0,944 | 0,942 | 0,942 | 0,942 | 0,938 | 0,942 |
