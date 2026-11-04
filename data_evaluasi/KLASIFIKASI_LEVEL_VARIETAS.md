# Klasifikasi level varietas data cabai (4 November 2026)

Keputusan peneliti: data cabai yang dipakai hanya yang namanya sampai **level varietas atau kultivar** (di bawah
spesies dan subspesies). Nama yang hanya sampai spesies, nama jenis umum, atau tanpa nama varietas dikeluarkan.

Catatan istilah: "varietas" di sini dipakai dalam arti budidaya (varietas terdaftar Kementan, varietas lokal,
kultivar bernama), bukan rank botani *var.* (mis. *C. annuum* var. *glabriusculum*). Menurut rank botani yang ketat,
tidak ada data di proyek ini yang memenuhi syarat.

Sejak 5 Nov 2026 dataset bersih (`dataset_eksperimen/`, `data_evaluasi/inputs/`) dan gold (`gold/`, `gambar/manifest/`,
`gambar_id/gold_peneliti/`, `klasifikasi_varietas_foto_commons_abu_abu.csv`) ikut di GitHub. Yang tetap lokal: folder
arsip `_dikeluarkan_bukan_varietas/` serta foto lain di `data_evaluasi/` (gambar, pilot PVT, sumber luar negeri).
Keputusan desainnya dicatat sebagai D19 di `docs/DESIGN_DECISIONS.md`.

## 1. Sudah dikeluarkan (gagal kriteria)

Tidak dihapus permanen. Berkas dipindah ke `<folder>/_dikeluarkan_bukan_varietas/<path asli>` di `data_evaluasi/`,
`dataset_eksperimen/`, dan `data_input_dummy/`. Workbook yang hanya sebagian barisnya gagal disalin utuh ke arsip,
lalu baris yang gagal dihapus. Daftar lengkapnya ada di `_dikeluarkan_bukan_varietas/DAFTAR_DIKELUARKAN.csv`, dan
skripnya di `skrip/keluarkan_non_varietas.py`. Backup sebelum perubahan:
`../../backup_sebelum_hapus_nonvarietas_2026-11-04.zip`, relatif dari folder `project/`.

| Data | Yang dikeluarkan | Alasan |
|---|---|---|
| R01 `data_input.xlsx` | seluruh berkas (3 salinan) | Kolom Jenis Cabai hanya "Cabai rawit (*C. frutescens*)" dan "cabai besar (*C. annuum*)" |
| S03 `D03_row_multilevel_indonesia.xlsx` | baris "Cabai rawit NTB" | Nama jenis + asal daerah |
| `spreadsheet_varietas_terdaftar.xlsx` (8) dan `_17.xlsx` | baris Cabai Rawit, Cabai Korea | Nama jenis umum dan asal negara |
| G01, G02 (GRIN) | baris Cabai Rawit, Cabai Korea (sheet data dan sumber) | Sama |
| Foto Commons | 58 foto (× 3 salinan): 35 UNCERTAIN, 11 Cabai Rawit (Bird's eye chili), 12 Cabai Korea generik | Tanpa nama varietas |
| Foto Indonesia | `C. annuum - bentuk buah...jpg`, `warna tangkai daun C. chinense dan C. annuum...jpg` | Hanya spesies |
| `gambar_id/kandidat_inat/` | seluruh folder (148 foto) | Hanya spesies (annuum/frutescens) |

**Tidak diubah:** gold (`gold/`, `gambar/manifest/`, `gambar_id/gold_*`), arsip zip foto Commons, hasil run
(`hasil_eksperimen/`, `4_hasil_sistem/`), dan `data/samples/data_input.xlsx`, yang dipakai kode dan tes. Baris gold
untuk item yang dikeluarkan masih ada. Gold dan skor perlu disaring ulang bila dataset bersih dipakai untuk paper.
ID butir gold S03 dihitung dari SHA-256 berkas, sehingga berubah karena isi D03 berubah.

## 2. Kelompok abu-abu: usulan nama level varietas (hasil riset)

Banyak nama dagang cabai sebenarnya adalah **tipe buah atau cultivar group**, bukan satu kultivar. Rujukan utama untuk
pembagian group dan kultivar *C. annuum* adalah Multilingual Multiscript Plant Name Database (Univ. Melbourne).

### 2a. Spreadsheet

| Nama sekarang | Status | Usulan level varietas |
|---|---|---|
| Cabai tanjung (S01, S03; data sintetis) | Tipe | Varietas resmi Balitsa **Tanjung-1** atau **Tanjung-2** (hasil pemurnian cabai besar lokal). Pilih salah satu; tidak bisa disimpulkan dari data sintetis |
| Zenodo: Tabasco, Etna ornamental, Pirâmide ornamental | Kultivar | Tetap (Etna dan Pirâmide adalah kultivar hias *C. frutescens*) |
| Zenodo: Bhut Jolokia | Kultivar/landrace | Tetap (Commons juga memperlakukannya sebagai kultivar *C. chinense*) |
| Zenodo: Habanero amarela / vermelha / chocolate | Tipe + warna | Tidak ada nama kultivar di sumber |
| Zenodo: Biquinho amarela / vermelha, Cumari do Pará, Murupi, Cheiro do Norte (pimenta-de-cheiro), Arari bode (pimenta-bode), Malagueta, Piãozinho | Tipe/landrace Brasil | Tidak ada nama kultivar. Sumber Zenodo hanya memuat nama umum (mis. `Cumari(C)`, `malagueta(F)`) dari skripsi Freire 2019, "17 commercial genotypes" |
| Zenodo: Peito de moça | Tipe; spesies diperdebatkan | Dataset menyebut *C. chinense*, penjual benih menyebut *C. baccatum* |
| Zenodo: Cayenne | Tipe | Cayenne Group; di dataset tercatat *C. frutescens*, padahal umumnya *C. annuum* |
| G01/G02 dan daftar foto: Jalapeño, Habanero, Cayenne, Serrano, Paprika, Scotch Bonnet, Banana Pepper | Tipe | Lihat 2b |
| Hungarian Wax | Kultivar | Tetap ('Hungarian Wax', Banana Group) |
| Poblano | Kultivar (sinonim) | 'Mexican Ancho' syn. 'Poblano' (Ancho Group) |

### 2b. Foto Commons (73 foto, rincian per foto: `klasifikasi_varietas_foto_commons_abu_abu.csv`)

| Label sekarang | Foto | Usulan |
|---|---|---|
| Cabai Korea (kategori Cheongyang) | 2 | **Ganti label menjadi 'Cheongyang'** (kultivar Korea, 1983) → lolos |
| Habanero | 2 dari 20 | **'Red Savina'** (judul Commons menyebut Red Savina) → lolos |
| Cayenne | 1 dari 9 | **'De Cayenne'** syn. 'Red Cayenne' (judul Commons: *Capsicum annuum 'de Cayenne'*) → lolos |
| Hungarian Wax | 7 | Kultivar 'Hungarian Wax' → lolos |
| Poblano | 2 | Kultivar 'Mexican Ancho' syn. 'Poblano' → lolos |
| Habanero (sisa 18), Jalapeño 13, Cayenne (sisa 8), Scotch Bonnet 6, Serrano 5, Banana Pepper 5, Paprika/bell 4 | 59 | Hanya tipe buah; kultivar tidak bisa ditentukan dari foto atau judulnya → kandidat dikeluarkan |

Ringkasan: dari 73 foto abu-abu, **14 bisa dinaikkan ke level kultivar** (2 di antaranya perlu ganti label), dan
**59 tetap hanya tipe**.

Foto Indonesia `p9vb80t0ldt5cms.webp`: label "Gendot" hanya tebakan AI. Ini tidak bisa diverifikasi lewat internet,
jadi keputusannya ada pada peneliti.

## 2c. Tahap 2 (5 November 2026): nama tipe ikut dikeluarkan

Keputusan peneliti: semua nama yang hanya sampai level tipe buah juga dikeluarkan (`skrip/keluarkan_non_varietas.py
--tahap2`). Arsip workbook yang sudah ada dari tahap 1 tidak ditimpa, sehingga arsip berisi versi asli.

| Data | Yang dikeluarkan | Sisa |
|---|---|---|
| Foto Commons | 59 foto berstatus TIPE (× 3 salinan) | 43 foto (14 kultivar + 27 OTHER kultivar + 2 foto yang sejak awal tidak masuk gold) |
| Daftar varietas foto (8) | Jalapeno, Habanero, Cayenne, Paprika, Serrano | Hungarian Wax |
| Daftar varietas foto (17) | + Scotch Bonnet, Banana Pepper | Hungarian Wax, Bhut Jolokia, Carolina Reaper, Trinidad Moruga Scorpion, Black Pearl, Padron, Poblano, Shishito |
| G01 / G02 (GRIN) | baris tipe yang sama | G01: Hungarian Wax; G02: Hungarian Wax, Poblano |
| N08 Zenodo (kedua berkas) | 13 genotipe tipe/landrace (65 baris) | Tabasco, Bhut Jolokia, Etna ornamental, Pirâmide ornamental (20 baris) |
| S01 D01 | kolom Cabai tanjung | Gendot, Kopay, Katokkon |
| S03 D03 | baris Cabai tanjung | Katokkon, Domba |

## 2d. Ganti label 5 foto ke nama kultivar (5 November 2026, keputusan peneliti)

Diubah di `gambar/manifest/gold_gambar_manifest_final.csv` (gold untuk skor). Salinan sebelum perubahan ada di
`gold_gambar_manifest_final.bak_sebelum_ganti_label_2026-11-05.csv`. Gold usulan AI (`gold_gambar_manifest.csv/.xlsx`)
dan hasil run tidak diubah.

| Foto | Sebelum | Sesudah |
|---|---|---|
| `cabai-rawit_buah_120.jpg`, `habanero_buah_110.jpg` | Cabai Korea, KNOWN/Y, REVIEW_MISMATCH | **Cheongyang**, OTHER/N, REVIEW_MISMATCH |
| `IMG_0022.jpg`, `IMG_0067.jpg` | Habanero, KNOWN/Y, AUTO_LINK | **Red Savina**, OTHER/N, CANDIDATE |
| `cayenne_buah_080.jpg` | Cayenne, KNOWN/Y, AUTO_LINK | **De Cayenne**, OTHER/N, CANDIDATE |

KNOWN/OTHER ikut berubah karena ketiga nama baru tidak ada di daftar varietas terdaftar mana pun (8 maupun 17 nama).
`expected_fusion` mengikuti pola gold yang sudah ada: OTHER + nama file menyesatkan menjadi REVIEW_MISMATCH, selain itu
CANDIDATE. Alasan perubahan dicatat di kolom `catatan_tinjauan`. Status KNOWN/OTHER di seluruh gold tetap perlu
ditinjau ulang setelah daftar varietas terdaftar yang baru ditetapkan.

## 2e. Riset nama lokal dan aksesi GRIN yang tersisa (5 November 2026)

| Nama | Kesimpulan | Bukti |
|---|---|---|
| Katokkon | ✅ Varietas lokal terdaftar | Terdaftar di Pusat PVTPP (varietas lokal Sulawesi Selatan, 2017; jurnal UKI Toraja). Nomor tanda daftar belum ditemukan |
| Kopay | ✅ Varietas terdaftar | Kepmentan 2085/Kpts/SR.120/5/2009 tentang Varietas Terdaftar Tanaman Hortikultura (dikutip jurnal Unida *Trading Analysis of the Kopay Chili*). Benih berlabel biru disertifikasi BPSB Sumbar. Tercantum di SIMCABAI Kementan (situsnya tidak bisa diakses untuk dicek langsung) |
| Gendot | ❌ Nama lokal untuk tipe | Sebutan lokal Bandung/Dieng untuk cabai tipe habanero (*C. chinense*); satu sumber menyebutnya *C. pubescens*. Muncul sebagai genotipe koleksi penelitian, tetapi tidak ditemukan tanda daftar atau SK pelepasan |
| Domba (cengek domba) | ❌ Nama lokal untuk tipe | Sebutan Sunda untuk rawit besar (*C. frutescens*, disebut juga cengek bodas). Tidak ditemukan tanda daftar atau SK |
| GRIN Hungarian Wax (PI 640679) | ✅ Kultivar | GRIN: nama 'Hungarian Yellow Wax', improvement status "Cultivar" |
| GRIN Poblano (PI 268105) | ❌ Tipe | GRIN: "Tipo Poblano" tercatat sebagai *local name*, tanpa nama kultivar dan tanpa improvement status (donasi Meksiko 1960) |

Catatan: database varietas terdaftar PPVTPP dan SIMCABAI tidak dapat dicari dari luar, sehingga ❌ untuk Gendot dan Domba
berarti "tidak ditemukan bukti pendaftaran", bukan bukti bahwa keduanya pasti tidak terdaftar. Jawa Barat tercatat
memiliki 204 varietas lokal terdaftar (Sinar Tani, 2025), tetapi daftar namanya tidak dipublikasikan.

## 3. Sumber
- Multilingual Multiscript Plant Name Database, *Capsicum annuum*: https://plantnames.unimelb.edu.au/Sorting/Capsicum_annuum.html
- Wikipedia, *Capsicum chinense* (Red Savina sebagai kultivar habanero): https://en.wikipedia.org/wiki/Capsicum_chinense
- Cheongyang chili pepper: https://wikiwand.com/simple/Cheongyang_chili_pepper
- Hungarian wax pepper: https://en.wikipedia.org/wiki/Hungarian_wax_pepper
- Balitsa, varietas Tanjung-1/Tanjung-2: https://media.neliti.com/media/publications/80584-ID-studi-adopsi-cabai-merah-varietas-tanjun.pdf ,
  https://media.neliti.com/media/publications/83649-ID-peningkatan-potensi-hasil-varietas-galur.pdf
- Embrapa, tipe *C. chinense* Brasil (cheiro, bode, cumari-do-Pará, biquinho, murupi): https://www.alice.cnptia.embrapa.br/alice/bitstream/doc/1027862/1/v.33n4201533410.pdf
- Etna (*C. frutescens*, kultivar hias): https://www.ingegnoli.it/eng/etna-hot-pepper-capsicum-frutescens.html
- Pirâmide (kultivar hias): https://mail.editorarealize.com.br/editora/anais/conapesc/2020/TRABALHO_EV138_MD1_SA25_ID539_07102020192202.pdf
- Peito de moça, Piãozinho (penjual benih, kurang andal): https://www.reimerseeds.com/piaozinho-pepper-seeds , https://www.reimerseeds.com/peppers-hot-brazil
- Zenodo 23395436 (nama genotipe asli, sheet Observed85/Protocol): https://zenodo.org/records/23395436
