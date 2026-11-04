# Eksperimen F2: skema kanonik dinamis (sementara; gold pra-anotasi AI)

Urutan run per pengulangan: R01, N07, N09, R02; database kosong di awal tiap pengulangan; 3 pengulangan.

## F2-1 akuisisi dan F2-2 penggunaan ulang (per pengulangan dan dataset)

| Rep | Dataset | Atribut | Kandidat dinilai | Baris baru | Duplikat dari baris ada | Bukan karakter | Gagal | Dipetakan ke baris akuisisi lama | Baris Excel |
|---|---|---|---|---|---|---|---|---|---|
| rep1 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 69 |
| rep1 | N07 | 69 | 49 | 37 | 1 | 11 | 0 | 0 | 95 |
| rep1 | N09 | 80 | 22 | 13 | 1 | 8 | 0 | 33 | 103 |
| rep1 | R02 | 53 | 10 | 1 | 1 | 8 | 0 | 26 | 104 |
| rep2 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 69 |
| rep2 | N07 | 69 | 49 | 41 | 0 | 8 | 0 | 0 | 98 |
| rep2 | N09 | 80 | 15 | 6 | 1 | 8 | 0 | 42 | 104 |
| rep2 | R02 | 53 | 10 | 2 | 0 | 8 | 0 | 26 | 106 |
| rep3 | R01 | 13 | 8 | 8 | 0 | 0 | 0 | 0 | 69 |
| rep3 | N07 | 69 | 49 | 37 | 1 | 11 | 0 | 0 | 95 |
| rep3 | N09 | 80 | 23 | 13 | 2 | 8 | 0 | 32 | 103 |
| rep3 | R02 | 53 | 9 | 1 | 0 | 8 | 0 | 26 | 104 |

## F2-4 pengaruh pada pemetaan template (Mapping F1 terhadap gold)

Prediksi pada baris akuisisi dihitung (a) sebagai prediksi berkunci (ketat: butir NO_MATCH yang diakuisisi menjadi salah positif) dan (b) diabaikan (tampilan hanya template). Pembanding: saklar mati, pengulangan 1.

| Dataset | F1 saklar mati | F1 saklar hidup (hanya template) | selisih | F1 saklar hidup (ketat) |
|---|---|---|---|---|
| R01 | 0.667 | 0.667 | +0.000 | 0.182 |
| N07 | 0.974 | 0.974 | +0.000 | 0.519 |
| N09 | 1.000 | 0.978 | -0.022 | 0.531 |
| R02 | 1.000 | 0.981 | -0.019 | 0.591 |

## F2-3 anti duplikat

- rep1: 43 baris akuisisi dari 89 kandidat atribut (tanpa penyatuan seharusnya sampai 89 baris); pasangan label sangat mirip: 4
  - 0.9: `bentuk penampang melintang buah` | `bentuk penampang melintang daun`
  - 0.81: `kelembapan tanah` | `kelembapan udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`
- rep2: 45 baris akuisisi dari 82 kandidat atribut (tanpa penyatuan seharusnya sampai 82 baris); pasangan label sangat mirip: 4
  - 0.9: `profil penampang melintang buah` | `profil penampang melintang daun`
  - 0.81: `kelembapan tanah` | `kelembapan udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`
- rep3: 43 baris akuisisi dari 89 kandidat atribut (tanpa penyatuan seharusnya sampai 89 baris); pasangan label sangat mirip: 3
  - 0.81: `kelembapan tanah` | `kelembapan udara`
  - 0.8: `ketahanan terhadap penyakit` | `ketahanan terhadap hama`
  - 0.79: `diameter batang` | `diameter buah`

## F2-5 stabilitas antar pengulangan

- rep1: 43 baris
- rep2: 45 baris
- rep3: 43 baris
- Kemiripan label rep1 vs rep2: Jaccard 0.66 (35 dari 53)
- Kemiripan label rep1 vs rep3: Jaccard 0.62 (33 dari 53)
- Kemiripan label rep2 vs rep3: Jaccard 0.57 (32 dari 56)

## Daftar baris akuisisi (pengulangan 1) untuk tinjauan kurator

- `kandungan_klorofil_daun` | kandungan klorofil daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Chlorophyll Content (SPAD) | run: faa9ba06
- `kandungan_nitrogen_daun` | kandungan nitrogen daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Nitrogen content (mg/g) | run: faa9ba06
- `kelembapan_permukaan_daun` | kelembapan permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Humidity (%) | run: faa9ba06
- `suhu_permukaan_daun` | suhu permukaan daun | daun | sumber: Mean (Rerata) Data Fisiologi Tanaman. Diukur pada permukaan daun cabai / Suhu permukaan daun(oC) | run: faa9ba06
- `kelembapan_tanah` | kelembapan tanah | vegetatif | sumber: Data ekologi tanah / Kelembaban tanah (%) | run: faa9ba06
- `ph_tanah` | pH tanah | vegetatif | sumber: Data ekologi tanah / pH tanah | run: faa9ba06
- `suhu_udara` | suhu udara | vegetatif | sumber: Data microclimate / Suhu udara (0C) | run: faa9ba06
- `kelembapan_udara` | kelembapan udara | vegetatif | sumber: Data microclimate / Kelembaban udara (%) | run: faa9ba06
- `bentuk_penampang_batang` | bentuk penampang batang | vegetatif | sumber: Bentuk penampang batang | run: e9911cc7
- `diameter_batang` | diameter batang | vegetatif | sumber: Diameter batang | run: e9911cc7
- `warna_batang` | warna batang | vegetatif | sumber: Warna batang | run: e9911cc7
- `intensitas_antosianin_buku_batang` | intensitas antosianin buku batang | vegetatif | sumber: Intensitas pewarnaan antosianin pada buku | run: e9911cc7
- `ukuran_daun` | ukuran daun | daun | sumber: Ukuran daun | run: e9911cc7
- `warna_kepala_putik` | warna kepala putik | bunga | sumber: kepala putik | run: e9911cc7
- `warna_benang_sari` | warna benang sari | bunga | sumber: benang sari | run: e9911cc7
- `umur_mulai_berbunga` | umur mulai berbunga | vegetatif | sumber: Umur mulai berbunga | run: e9911cc7
- `umur_mulai_panen` | umur mulai panen | vegetatif | sumber: Umur mulai panen | run: e9911cc7
- `ukuran_buah` | ukuran buah | buah | sumber: Ukuran buah | run: e9911cc7
- `tebal_perikarp_buah` | tebal perikarp buah | buah | sumber: Tebal kulit buah | run: e9911cc7
- `rasa_buah` | rasa buah | buah | sumber: Rasa buah | run: e9911cc7
- `bentuk_biji` | bentuk biji | biji | sumber: Bentuk biji | run: e9911cc7
- `berat_1000_biji` | berat 1000 biji | biji | sumber: Berat 1000 biji | run: e9911cc7
- `bobot_per_buah` | bobot per buah | buah | sumber: Berat per buah | run: e9911cc7
- `jumlah_buah_per_tanaman` | jumlah buah per tanaman | buah | sumber: Jumlah buah per tanaman | run: e9911cc7
- `bobot_buah_per_tanaman` | bobot buah per tanaman | buah | sumber: Berat buah per tanaman | run: e9911cc7
- `ketahanan_terhadap_penyakit` | ketahanan terhadap penyakit | vegetatif | sumber: Ketahanan terhadap penyakit | run: e9911cc7
- `daya_simpan_buah` | daya simpan buah | buah | sumber: Daya simpan buah pada suhu 24-27Â°C | run: e9911cc7
- `potensi_hasil_per_hektar` | potensi hasil per hektar | buah | sumber: Hasil buah per hektar | run: e9911cc7
- `tinggi_dikotomus` | tinggi dikotomus | vegetatif | sumber: Tinggi dikotomus | run: e9911cc7
- `lebar_tajuk` | lebar tajuk | vegetatif | sumber: Lebar tajuk | run: e9911cc7
- `pemendekan_ruas_batang` | pemendekan ruas batang | vegetatif | sumber: Pemendekan ruas-internode | run: e9911cc7
- `kedudukan_kepala_putik_terhadap_benang_sari` | kedudukan kepala putik terhadap benang sari | bunga | sumber: Posisi stigma terhadap anther | run: e9911cc7
- `diameter_buah` | diameter buah | buah | sumber: Diameter buah | run: e9911cc7
- `warna_buah_intermediate` | warna buah intermediate | buah | sumber: Warna buah intermediate | run: e9911cc7
- `ketahanan_terhadap_hama` | ketahanan terhadap hama | vegetatif | sumber: Ketahanan terhadap hama | run: 86a3e93e
- `populasi_per_hektar` | populasi per hektar | vegetatif | sumber: Populasi per hektar | run: 86a3e93e
- `kebutuhan_benih_per_hektar` | kebutuhan benih per hektar | biji | sumber: Kebutuhan benih per hektar | run: 86a3e93e
- `orientasi_buah` | orientasi buah | buah | sumber: Tipe Berbuah | run: 86a3e93e
- `panjang_dikotomus` | panjang dikotomus | vegetatif | sumber: Panjang dikotomus | run: 86a3e93e
- `panjang_ruas_batang` | panjang ruas batang | vegetatif | sumber: Panjang ruas batang | run: 86a3e93e
- `bentuk_penampang_melintang_buah` | bentuk penampang melintang buah | buah | sumber: Profil potongan melintang | run: 86a3e93e
- `panjang_buah` | panjang buah | buah | sumber: Panjang buah | run: 86a3e93e
- `bentuk_penampang_melintang_daun` | bentuk penampang melintang daun | daun | sumber: Profil potongan melintang daun | run: 48dd08f7
