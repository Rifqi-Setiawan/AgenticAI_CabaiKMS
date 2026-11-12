# Eksperimen F2: skema kanonik dinamis (sementara)

Urutan run per pengulangan: R01, N07, N09, R02; database kosong di awal tiap pengulangan; 3 pengulangan.

## F2-1 akuisisi dan F2-2 penggunaan ulang (per pengulangan dan dataset)

| Rep | Dataset | Atribut | Kandidat dinilai | Baris baru | Duplikat (tak ditulis) | Digabung ke baris ada | Bukan karakter | Gagal | Dipetakan ke baris akuisisi lama | Baris Excel |
|---|---|---|---|---|---|---|---|---|---|---|
| rep1 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep1 | N07 | 69 | 49 | 28 | 0 | 13 | 8 | 0 | 0 | 97 |
| rep1 | N09 | 80 | 16 | 4 | 0 | 4 | 8 | 0 | 39 | 101 |
| rep1 | R02 | 53 | 11 | 0 | 0 | 3 | 8 | 0 | 24 | 101 |
| rep2 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep2 | N07 | 69 | 49 | 28 | 0 | 13 | 8 | 0 | 0 | 97 |
| rep2 | N09 | 80 | 17 | 4 | 0 | 5 | 8 | 0 | 39 | 101 |
| rep2 | R02 | 53 | 11 | 0 | 0 | 3 | 8 | 0 | 24 | 101 |
| rep3 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 0 | 69 |
| rep3 | N07 | 69 | 49 | 28 | 0 | 13 | 8 | 0 | 0 | 97 |
| rep3 | N09 | 80 | 16 | 4 | 0 | 4 | 8 | 0 | 39 | 101 |
| rep3 | R02 | 53 | 11 | 0 | 0 | 3 | 8 | 0 | 24 | 101 |

## F2-4 pengaruh pada pemetaan template (Mapping F1 terhadap gold)

Prediksi pada baris akuisisi dihitung (a) sebagai prediksi berkunci (ketat: butir NO_MATCH yang diakuisisi menjadi salah positif) dan (b) diabaikan (tampilan hanya template). Pembanding: saklar mati, pengulangan 1.

| Dataset | F1 saklar mati | F1 saklar hidup (hanya template) | selisih | F1 saklar hidup (ketat) |
|---|---|---|---|---|
| R01 | 0.667 | 0.667 | +0.000 | 0.182 |
| N07 | 0.974 | 1.000 | +0.026 | 0.526 |
| N09 | 1.000 | 1.000 | +0.000 | 0.545 |
| R02 | 1.000 | 1.000 | +0.000 | 0.610 |

## F2-3 anti duplikat

- rep1: 40 baris akuisisi dari 84 kandidat atribut (tanpa penyatuan seharusnya sampai 84 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembaban tanah` | `kelembaban udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`
- rep2: 40 baris akuisisi dari 85 kandidat atribut (tanpa penyatuan seharusnya sampai 85 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembapan tanah` | `kelembapan udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`
- rep3: 40 baris akuisisi dari 84 kandidat atribut (tanpa penyatuan seharusnya sampai 84 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembaban tanah` | `kelembaban udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`

## F2-5 stabilitas antar pengulangan

- rep1: 40 baris
- rep2: 40 baris
- rep3: 40 baris
- Kemiripan label rep1 vs rep2: Jaccard 0.78 (35 dari 45)
- Kemiripan label rep1 vs rep3: Jaccard 0.78 (35 dari 45)
- Kemiripan label rep2 vs rep3: Jaccard 0.70 (33 dari 47)

## Daftar baris akuisisi (pengulangan 1) untuk tinjauan kurator

- `kandungan_klorofil_daun` | kandungan klorofil daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Chlorophyll Content (SPAD) | run: 5d833507
- `kandungan_nitrogen_daun` | kandungan nitrogen daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Nitrogen content (mg/g) | run: 5d833507
- `kelembapan_permukaan_daun` | kelembapan permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Humidity (%) | run: 5d833507
- `suhu_permukaan_daun` | suhu permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Suhu permukaan daun(oC) | run: 5d833507
- `kelembaban_tanah` | kelembaban tanah | vegetatif | sumber: Data ekologi tanah / Kelembaban tanah (%) | run: 5d833507
- `ph_tanah` | pH tanah | vegetatif | sumber: Data ekologi tanah / pH tanah | run: 5d833507
- `suhu_udara` | suhu udara | vegetatif | sumber: Data microclimate / Suhu udara (0C) | run: 5d833507
- `kelembaban_udara` | kelembaban udara | vegetatif | sumber: Data microclimate / Kelembaban udara (%) | run: 5d833507
- `bentuk_penampang_batang` | bentuk penampang batang | vegetatif | sumber: Bentuk penampang batang | run: 3f401d60
- `diameter_batang` | diameter batang | vegetatif | sumber: Diameter batang | run: 3f401d60
- `warna_batang` | warna batang | vegetatif | sumber: Warna batang | run: 3f401d60
- `intensitas_antosianin_buku_batang` | intensitas antosianin buku batang | vegetatif | sumber: Intensitas pewarnaan antosianin pada buku | run: 3f401d60
- `ukuran_daun` | ukuran daun | daun | sumber: Ukuran daun | run: 3f401d60
- `warna_kepala_putik` | warna kepala putik | bunga | sumber: kepala putik | run: 3f401d60
- `warna_benang_sari` | warna benang sari | bunga | sumber: benang sari | run: 3f401d60
- `umur_mulai_berbunga` | umur mulai berbunga | vegetatif | sumber: Umur mulai berbunga | run: 3f401d60
- `umur_mulai_panen` | umur mulai panen | vegetatif | sumber: Umur mulai panen | run: 3f401d60
- `ukuran_buah` | ukuran buah | buah | sumber: Ukuran buah | run: 3f401d60
- `tebal_kulit_buah` | tebal kulit buah | buah | sumber: Tebal kulit buah | run: 3f401d60
- `rasa_buah` | rasa buah | buah | sumber: Rasa buah | run: 3f401d60
- `bentuk_biji` | bentuk biji | biji | sumber: Bentuk biji | run: 3f401d60
- `bobot_1000_biji` | bobot 1000 biji | biji | sumber: Berat 1000 biji | run: 3f401d60
- `bobot_per_buah` | bobot per buah | buah | sumber: Berat per buah | run: 3f401d60
- `jumlah_buah_per_tanaman` | jumlah buah per tanaman | buah | sumber: Jumlah buah per tanaman | run: 3f401d60
- `bobot_buah_per_tanaman` | bobot buah per tanaman | buah | sumber: Berat buah per tanaman | run: 3f401d60
- `ketahanan_terhadap_penyakit` | ketahanan terhadap penyakit | vegetatif | sumber: Ketahanan terhadap penyakit | run: 3f401d60
- `daya_simpan_buah` | daya simpan buah | buah | sumber: Daya simpan buah pada suhu 24-27Â°C | run: 3f401d60
- `hasil_buah_per_hektar` | hasil buah per hektar | buah | sumber: Hasil buah per hektar | run: 3f401d60
- `populasi_per_hektar` | populasi per hektar | vegetatif | sumber: Populasi per hektar | run: 3f401d60
- `kebutuhan_benih_per_hektar` | kebutuhan benih per hektar | biji | sumber: Kebutuhan benih per hektar | run: 3f401d60
- `tinggi_dikotomus` | tinggi dikotomus | vegetatif | sumber: Tinggi dikotomus | run: 3f401d60
- `lebar_tajuk` | lebar tajuk | vegetatif | sumber: Lebar tajuk | run: 3f401d60
- `pemendekan_ruas_batang` | pemendekan ruas batang | vegetatif | sumber: Pemendekan ruas-internode | run: 3f401d60
- `posisi_putik_terhadap_benang_sari` | posisi putik terhadap benang sari | bunga | sumber: Posisi stigma terhadap anther | run: 3f401d60
- `diameter_buah` | diameter buah | buah | sumber: Diameter buah | run: 3f401d60
- `warna_buah_peralihan` | warna buah peralihan | buah | sumber: Warna buah intermediate | run: 3f401d60
- `ketahanan_terhadap_hama` | ketahanan terhadap hama | vegetatif | sumber: Ketahanan terhadap hama | run: 6acb83bc
- `panjang_ruas_batang` | panjang ruas batang | vegetatif | sumber: Panjang ruas batang | run: 6acb83bc
- `profil_penampang_melintang_daun` | profil penampang melintang daun | daun | sumber: Profil potongan melintang | run: 6acb83bc
- `orientasi_pedunkulus` | orientasi pedunkulus | bunga | sumber: Orientasi pedunkulus | run: 6acb83bc
