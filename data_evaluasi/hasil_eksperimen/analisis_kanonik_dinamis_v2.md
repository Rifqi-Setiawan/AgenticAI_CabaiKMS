# Eksperimen F2: skema kanonik dinamis (sementara)

Urutan run per pengulangan: R01, N07, N09, R02; database kosong di awal tiap pengulangan; 3 pengulangan.

## F2-1 akuisisi dan F2-2 penggunaan ulang (per pengulangan dan dataset)

| Rep | Dataset | Atribut | Kandidat dinilai | Baris baru | Duplikat (tak ditulis) | Digabung ke baris ada | Bukan karakter | Gagal | Dipetakan ke baris akuisisi lama | Baris Excel |
|---|---|---|---|---|---|---|---|---|---|---|
| rep1 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep1 | N07 | 69 | 49 | 0 | 0 | 0 | 0 | 49 | 0 | 69 |
| rep1 | N09 | 80 | 54 | 0 | 0 | 0 | 0 | 54 | 0 | 69 |
| rep1 | R02 | 53 | 35 | 27 | 0 | 0 | 8 | 0 | 0 | 96 |
| rep2 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep2 | N07 | 69 | 49 | 39 | 0 | 1 | 9 | 0 | 0 | 96 |
| rep2 | N09 | 80 | 19 | 6 | 0 | 5 | 8 | 0 | 36 | 100 |
| rep2 | R02 | 53 | 12 | 0 | 0 | 4 | 8 | 0 | 23 | 100 |
| rep3 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep3 | N07 | 69 | 49 | 0 | 0 | 0 | 0 | 49 | 0 | 69 |
| rep3 | N09 | 80 | 55 | 0 | 0 | 0 | 0 | 55 | 0 | 69 |
| rep3 | R02 | 53 | 35 | 0 | 0 | 0 | 0 | 35 | 0 | 69 |

## F2-4 pengaruh pada pemetaan template (Mapping F1 terhadap gold)

Prediksi pada baris akuisisi dihitung (a) sebagai prediksi berkunci (ketat: butir NO_MATCH yang diakuisisi menjadi salah positif) dan (b) diabaikan (tampilan hanya template). Pembanding: saklar mati, pengulangan 1.

| Dataset | F1 saklar mati | F1 saklar hidup (hanya template) | selisih | F1 saklar hidup (ketat) |
|---|---|---|---|---|
| R01 | 0.667 | 0.667 | +0.000 | 0.182 |
| N07 | 0.974 | 0.983 | +0.009 | 0.827 |
| N09 | 1.000 | 1.000 | +0.000 | 0.848 |
| R02 | 1.000 | 1.000 | +0.000 | 0.740 |

## F2-3 anti duplikat

- rep1: 35 baris akuisisi dari 146 kandidat atribut (tanpa penyatuan seharusnya sampai 146 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembaban tanah` | `kelembaban udara`
  - 0.8: `ketahanan terhadap hama` | `ketahanan terhadap penyakit`
  - 0.79: `diameter buah` | `diameter batang`
- rep2: 39 baris akuisisi dari 88 kandidat atribut (tanpa penyatuan seharusnya sampai 88 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembapan tanah` | `kelembapan udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`
- rep3: 8 baris akuisisi dari 147 kandidat atribut (tanpa penyatuan seharusnya sampai 147 baris); pasangan label sangat mirip: 1
  - 0.81: `kelembaban tanah` | `kelembaban udara`

## F2-5 stabilitas antar pengulangan

- rep1: 35 baris
- rep2: 39 baris
- rep3: 8 baris
- Kemiripan label rep1 vs rep2: Jaccard 0.51 (25 dari 49)
- Kemiripan label rep1 vs rep3: Jaccard 0.23 (8 dari 35)
- Kemiripan label rep2 vs rep3: Jaccard 0.09 (4 dari 43)

## Daftar baris akuisisi (pengulangan 1) untuk tinjauan kurator

- `kandungan_klorofil_daun` | kandungan klorofil daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Chlorophyll Content (SPAD) | run: dc1148ce
- `kandungan_nitrogen_daun` | kandungan nitrogen daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Nitrogen content (mg/g) | run: dc1148ce
- `kelembaban_permukaan_daun` | kelembaban permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Humidity (%) | run: dc1148ce
- `suhu_permukaan_daun` | suhu permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Suhu permukaan daun(oC) | run: dc1148ce
- `kelembaban_tanah` | kelembaban tanah | vegetatif | sumber: Data ekologi tanah / Kelembaban tanah (%) | run: dc1148ce
- `ph_tanah` | pH tanah | vegetatif | sumber: Data ekologi tanah / pH tanah | run: dc1148ce
- `suhu_udara` | suhu udara | vegetatif | sumber: Data microclimate / Suhu udara (0C) | run: dc1148ce
- `kelembaban_udara` | kelembaban udara | vegetatif | sumber: Data microclimate / Kelembaban udara (%) | run: dc1148ce
- `diameter_buah` | diameter buah | buah | sumber: Fruit diameter | run: d5697a3a
- `diameter_batang` | diameter batang | vegetatif | sumber: Stem diameter | run: d5697a3a
- `tebal_daging_buah` | tebal daging buah | buah | sumber: Pericarp thickness | run: d5697a3a
- `ukuran_daun` | ukuran daun | daun | sumber: Leaf size as recorded | run: d5697a3a
- `bobot_buah_masak` | bobot buah masak | buah | sumber: Mature fruit weight | run: d5697a3a
- `profil_penampang_melintang_daun` | profil penampang melintang daun | daun | sumber: Profil potongan melintang daun | run: d5697a3a
- `warna_batang` | warna batang | vegetatif | sumber: Warna batang | run: d5697a3a
- `bentuk_penampang_batang` | bentuk penampang batang | vegetatif | sumber: Bentuk penampang batang | run: d5697a3a
- `panjang_dikotomus` | panjang dikotomus | vegetatif | sumber: Panjang dikotomus | run: d5697a3a
- `panjang_ruas_batang` | panjang ruas batang | vegetatif | sumber: Panjang ruas batang | run: d5697a3a
- `warna_kepala_putik` | warna kepala putik | bunga | sumber: Warna kepala putik | run: d5697a3a
- `warna_benang_sari` | warna benang sari | bunga | sumber: Warna benang sari | run: d5697a3a
- `orientasi_tangkai_buah` | orientasi tangkai buah | buah | sumber: Orientasi pedunkulus | run: d5697a3a
- `posisi_buah` | posisi buah | buah | sumber: Tipe berbuah | run: d5697a3a
- `umur_mulai_berbunga` | umur mulai berbunga | vegetatif | sumber: Umur mulai berbunga | run: d5697a3a
- `umur_mulai_panen` | umur mulai panen | vegetatif | sumber: Umur mulai panen | run: d5697a3a
- `rasa_buah` | rasa buah | buah | sumber: Rasa buah | run: d5697a3a
- `bentuk_biji` | bentuk biji | biji | sumber: Bentuk biji | run: d5697a3a
- `bobot_1000_biji` | bobot 1000 biji | biji | sumber: Berat 1.000 biji | run: d5697a3a
- `jumlah_buah_per_tanaman` | jumlah buah per tanaman | buah | sumber: Jumlah buah per tanaman | run: d5697a3a
- `bobot_buah_per_tanaman` | bobot buah per tanaman | buah | sumber: Berat buah per tanaman | run: d5697a3a
- `daya_simpan_buah` | daya simpan buah | buah | sumber: Daya simpan buah | run: d5697a3a
- `ketahanan_terhadap_hama` | ketahanan terhadap hama | vegetatif | sumber: Ketahanan terhadap hama | run: d5697a3a
- `ketahanan_terhadap_penyakit` | ketahanan terhadap penyakit | vegetatif | sumber: Ketahanan terhadap penyakit | run: d5697a3a
- `hasil_buah_per_hektar` | hasil buah per hektar | buah | sumber: Hasil buah per hektar | run: d5697a3a
- `populasi_tanaman_per_hektar` | populasi tanaman per hektar | vegetatif | sumber: Populasi per hektar | run: d5697a3a
- `kebutuhan_benih_per_hektar` | kebutuhan benih per hektar | biji | sumber: Kebutuhan benih per hektar | run: d5697a3a
