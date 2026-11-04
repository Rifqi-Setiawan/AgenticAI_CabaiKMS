# Bagian tanaman 160 foto Commons: gold peneliti dan akurasi sistem

Gold: anotasi buta peneliti (4 Nov 2026), `gold/bagian_foto_commons/gold_bagian_commons.csv`. Prediksi: `identified_part` hasil terkoreksi D18. Bagian dianggap benar bila sama dengan bagian_utama atau bagian_lain (hanya empat kelas sistem). Foto TANAMAN_UTUH tanpa bagian kedua dan foto LAIN tidak dinilai.

## Gold peneliti

bagian_utama: BUAH 128, TANAMAN_UTUH 12, DAUN 10, BUNGA 7, LAIN 3

Tidak dinilai untuk bagian: 14 foto (TANAMAN_UTUH tanpa bagian kedua 11, LAIN 3).

Kesesuaian dengan label bagian lama (dari judul foto): bagian_utama sama 135/160; label lama termasuk bagian yang boleh 136/160.

## Akurasi bagian tanaman sistem

| Himpunan | Benar / dinilai |
|---|---|
| Semua foto | 140/146 = 0.959 |
| Foto yang ditautkan otomatis (AUTO_LINK) | 79/80 = 0.988 |
| gold utama DAUN | 5/10 = 0.500 |
| gold utama BATANG | - |
| gold utama BUAH | 128/128 = 1.000 |
| gold utama BUNGA | 7/7 = 1.000 |

Matriks (baris = gold bagian_utama, kolom = prediksi sistem), semua 160 foto:

| gold \ sistem | DAUN | BATANG | BUAH | BUNGA |
|---|---|---|---|---|
| BUAH | 1 | 0 | 127 | 0 |
| DAUN | 4 | 0 | 5 | 1 |
| BUNGA | 0 | 0 | 0 | 7 |
| TANAMAN_UTUH | 1 | 0 | 11 | 0 |
| LAIN | 1 | 0 | 2 | 0 |
