# Data Evaluasi CABAI-KMS: Input dan Gold Anotasi

Disusun 29 Oktober 2026, status diperbarui 1 November 2026. Folder ini berisi sembilan workbook input untuk evaluasi pemetaan atribut
(`inputs/`) dan anotasi gold untuk seluruh atributnya (`gold/`). File di `data_input_dummy/` tidak diubah;
semuanya disalin ke `inputs/` dengan isi yang sama (SHA-256 identik).

> **Status gold (diperbarui 1 November 2026).** Berkas `gold/gold_semua_dataset.*` adalah usulan awal satu anotator AI
> (`ai_single_annotator_v1`) dan dipertahankan sebagai pembanding. **Gold yang dipakai untuk skor** adalah
> `gold/final/gold_semua_dataset_final.csv` (sumber `ai_assisted_human_verified_v1`, reviewer peneliti): 326 butir, seluruh usulan disetujui tanpa perubahan (0%).
> Foto: `gambar/manifest/gold_gambar_manifest_final.csv` (sumber `ai_visual_review_v1`, tinjauan visual model, 158 foto). Keduanya **bukan** gold dua anotator manusia independen
> seperti yang diminta protokol proyek (`docs/HUMAN_ANNOTATION_GUIDE.md`, Bab III proposal); sebut ini di metodologi. Butir `perlu_adjudikasi = Y` (57 dari 326) disarankan diperiksa lebih dulu.
> Lembar verifikasi dan skripnya: `verifikasi_gold/`, `skrip/terapkan_verifikasi.py`.

> **Pembersihan level varietas (4-5 November 2026, D19).** Data yang hanya sampai spesies atau tipe buah (mis. R01, Cabai Rawit/Korea,
> Jalapeño, Habanero, foto UNCERTAIN) sudah dipindah ke `_dikeluarkan_bukan_varietas/`. Inventaris di bawah masih menggambarkan
> data sebelum pembersihan. Rincian: `KLASIFIKASI_LEVEL_VARIETAS.md`.

## 1. Inventaris dataset

| ID | Berkas | Sheet | Format (UI) | Header | Atribut | Asal |
|---|---|---|---|---|---|---|
| R01 | `data_input.xlsx` | Resume Data | row-oriented | otomatis (2 baris, sel gabungan) | 14 | Data riset lapangan (asli, milik Rifqi) |
| R02 | `input_cabai_kms.xlsx` | Data Varietas | row-oriented | 1 | 54 | Gabungan struktur Zenodo + isi deskripsi Kementan (disusun 26 Okt 2026) |
| S01 | `D01_transposed_indonesia_mixed.xlsx` | Data_Transposed | transposed | baris "Karakter" | 21 | Sintetis (dummy) |
| S02 | `D02_row_flat_english_semantic.xlsx` | English_Flat_Data | row-oriented | 1 | 26 | Sintetis, label Inggris dengan makna sama dengan S01 |
| S03 | `D03_row_multilevel_indonesia.xlsx` | Data_Bertingkat | row-oriented | 2 (bertingkat) | 30 | Sintetis, header dua tingkat |
| S04 | `D04_varietas_kosong_invalid.xlsx` | Data_Invalid | row-oriented | 1 | 8 | Sintetis, satu baris tanpa varietas |
| N07 | `E07_kementan_deskripsi_ext.xlsx` | Deskripsi Varietas | row-oriented | 1 | 70 | **Baru.** Tiga SK/deskripsi Kementan, label persis seperti di dokumen |
| N08 | `E08_zenodo_capsicum_en.xlsx` | Observed85_readable | row-oriented | 1 | 23 | **Baru.** Zenodo Capsicum (data nyata, 85 baris, label deskriptor Inggris) |
| N09 | `dataset_cabai_deskripsi_varietas.xlsx` | transposed | transposed | baris "Karakter" | 80 | 80 label asli dokumen untuk 6 varietas (disusun 26 Okt 2026) |

Total **326 butir atribut**. Jumlah atribut mengikuti keluaran parser proyek (`source_parsing.py`), bukan hitungan
manual; mis. `data_input.xlsx` menghasilkan 14 butir.

SHA-256:

| Berkas | SHA-256 |
|---|---|
| data_input.xlsx | `71e86f98a416d2f269b873c3a2c96bc729837fac0b104a79089e9d70fd093056` |
| input_cabai_kms.xlsx | `5b4a748b0dc99f7db66d8d95d544e8742a9a194a52eafec6ce32ca023613fb61` |
| D01_transposed_indonesia_mixed.xlsx | `7e4eb51952340a5968bfbb161325f9285b477d04924c392b1fbf988a5956e1c6` |
| D02_row_flat_english_semantic.xlsx | `3a0c788361e084f578c43c1a3125b2b25f62d78511db1000e342f54cc52cd559` |
| D03_row_multilevel_indonesia.xlsx | `b7f5fdbff40d7362df0020fafede6190ac4350d555fbb33c17206e684129e502` |
| D04_varietas_kosong_invalid.xlsx | `7f659f4a4050177f189e5da62ce4d417a6e163e9bd0ee8164d5f1d6dab1651bd` |
| E07_kementan_deskripsi_ext.xlsx | `c51a666839233718b301617aa03bd069acaf3aab20305aa8129a1475c246d320` |
| E08_zenodo_capsicum_en.xlsx | `57935abbae27c274cdfa61df259fc8027ae3d10f5d78917b48de60d8b3d86be3` |
| dataset_cabai_deskripsi_varietas.xlsx | `bd7875dd13fa2350105334a40f46ad209a6d7c1ec672c25f21f1e7e6c0913612` |

## 2. Sumber data baru

### E07: deskripsi varietas Kementan (tiga varietas)

Nilai disalin apa adanya dari dokumen resmi; label juga dipertahankan persis, termasuk label yang tidak seragam antar
dokumen (mis. `Warna kelopak bunga` vs `Warna bunga kelopak` vs `Kelopak`; `Bobot per buah` vs `Berat per buah`).
Kolom jarang terisi karena tiap dokumen memakai label berbeda. Itu disengaja: uji variasi label.

| Varietas | Dokumen | SHA-256 PDF | Tautan |
|---|---|---|---|
| Biocalya-Agrihorti (cabai merah) | Kepmentan 448/Kpts/PV.240/D/XII/2022, 13 Des 2022; BRMP Biogen | `5806931c...076074f`* | [PDF](https://biogen.brmp.pertanian.go.id/informasi-publik/download/varietas/deskripsi-cabai-merah-besar-varietas-biocalya) |
| ENNO009 (cabai rawit) | Kepmentan 415/Kpts/PV.240/D/V/2024; Ditjen Hortikultura (JDIH) | `5008f650...85b2cf`* | [PDF](https://hortikultura.pertanian.go.id/jdih/upload/peraturan/peraturan-1725324775.pdf) |
| Arisa IPB (cabai besar) | Kepmentan 492/Kpts/PV.240/D/VII/2024; Ditjen Hortikultura (JDIH) | `eb26689e...48c176`* | [PDF](https://hortikultura.pertanian.go.id/jdih/upload/peraturan/peraturan-1725325323.pdf) |

\* SHA-256 diringkas; nilai lengkap: Biocalya `5806931cddd436ec04b45d823a306bce54bd70ffbe4da4a97bdeb1086c76074f`,
ENNO009 `5008f6506ba723c31f57eca317d96be4672ec74df93b694752fd679c5485b2cf`,
Arisa `eb26689eee3b967ace30c649619bf416bae97d5c96e4264d1b5d18679648c176`.

Metode ekstraksi: Biocalya dari lapisan teks vektor PDF (`pdftotext -layout`); ENNO009 dan Arisa IPB adalah pindaian,
nilai dibaca dari **gambar halaman lampiran** (bukan dari teks OCR yang tidak andal).

Anomali yang dipertahankan: Biocalya `Ukuran daun` bernilai `P : 9,73-6,03 cm` (rentang terbalik) dan
`Berat 1000 biji` `9,41-5,48 g` (rentang terbalik); label Biocalya `Warna bunga kelopak` dibaca persis seperti
tercetak (urutan kata mungkin akibat pembungkusan baris); format desimal Arisa memakai titik, dokumen lain koma.
Biocalya tidak memuat Pemohon/Pemulia/Peneliti pada teks yang tersedia (sel dikosongkan). Syarat penggunaan ulang
dokumen pemerintah ini belum diperiksa.

### E08: Zenodo Capsicum (data nyata berbahasa Inggris)

Sheet `Observed85` dari *Capsicum_Supplementary_Data.xlsx* ([Zenodo 23395436](https://zenodo.org/records/23395436),
CC BY 4.0; Pinto Ribeiro, W. et al., Univ. Federal de Itajubá/Viçosa). Kolom bersandi (`x1_cm`...) diganti nama
deskriptor Inggris dari sheet `Descriptors` agar bisa dipetakan secara semantik; 85 baris pengamatan, 17 genotipe.
Nilai kategorikal tetap berupa kode angka (bukan teks). Kolom ulangan dan catatan kurasi tidak dipakai.
Atribusi ke pengarang wajib bila dipublikasikan.

### Ditemukan tetapi belum bisa dipakai

| Sumber | Alasan |
|---|---|
| Genesys CATIE 2008-2010 (61 sifat, Spanyol/Inggris), [halaman](https://www.genesys-pgr.org/datasets/36606ecb-e8b8-46bd-ba38-65ad6f2db024) | Berkas xlsx hanya tampil lewat antarmuka JavaScript; tautan unduhan langsung tidak tersedia. CC BY-NC 4.0 |
| Genesys CATIE 2011-2012 (57 sifat), [halaman](https://www.genesys-pgr.org/datasets/4247dcd4-d350-4455-92f4-40226ce0d595) | Sama |
| Genesys WorldVeg Capsicum (88 sifat, 5.270 aksesi), [halaman](https://www.genesys-pgr.org/datasets/f4341cb8-6488-4520-b7d1-72637a6f35d8) | Sama; lintas spesies |
| benih.pertanian.go.id (CR609, Brahma F1, CR 29425) | Server menjawab HTTP 520/error pada setiap percobaan |
| Zenodo 10.5281/zenodo.10619790 (parameter morfologi paprika, CSV) | Hanya tinggi dan diameter tajuk; keragaman atribut terlalu kecil |

Untuk mengambil berkas Genesys perlu unduhan manual lewat browser (akun/persetujuan). Bila sudah ada, parser dan
skrip pembuat gold di folder ini dapat dipakai ulang.

## 3. Gold anotasi

Berkas di `gold/`:

- `gold_semua_dataset.xlsx`: sheet `Annotations` (326 butir), `Ringkasan`, `Cakupan Kanonik`, `Canonical Reference`, `README`.
- `gold_semua_dataset.csv`: isi sheet Annotations (UTF-8 BOM).
- `gold_<ID>_<nama>.xlsx`: satu berkas per dataset, format sheet `Annotations` + `Canonical Reference`.

`mapping_item_id` dihitung dengan fungsi proyek (`src/schema/gold_mapping.py`) dari SHA-256 berkas, nama sheet,
format, dan label tampil atribut, sehingga cocok dengan ID yang dihasilkan pipeline untuk berkas yang sama. Jangan
mengubah isi berkas input; hash berubah maka ID tidak cocok. Validasi: ID penuh di sini (64 karakter) berawalan sama dengan
ID 40 karakter pada workbook pilot `eval/campaigns/schema-mapping-pilot-v1` untuk `data_input.xlsx`
(contoh butir Nitrogen: `bd4a71165945894465b8c8eaac0d0787f6da6e98...`), jadi kampanye pilot memotong ID menjadi 40 karakter.

Distribusi status:

| Dataset | Butir | ONE_TO_ONE | NO_MATCH | AMBIGUOUS | COMPOSITE | Perlu adjudikasi |
|---|---|---|---|---|---|---|
| R01 data_input | 14 | 1 | 13 | 0 | 0 | 4 |
| R02 input_cabai_kms | 54 | 18 | 32 | 3 | 1 | 11 |
| S01 D01 | 21 | 20 | 1 | 0 | 0 | 0 |
| S02 D02 | 26 | 22 | 4 | 0 | 0 | 0 |
| S03 D03 | 30 | 28 | 2 | 0 | 0 | 0 |
| S04 D04 | 8 | 6 | 2 | 0 | 0 | 0 |
| N07 E07 | 70 | 20 | 45 | 4 | 1 | 16 |
| N08 E08 | 23 | 9 | 12 | 2 | 0 | 5 |
| N09 label 80 dokumen | 80 | 24 | 48 | 7 | 1 | 21 |
| **Total** | **326** | **148** | **159** | **16** | **3** | **57** |

Temuan penting untuk desain evaluasi:

1. **Hanya 38 dari 59 baris kanonik muncul sebagai target gold.** Dua puluh satu kunci tidak pernah dipakai
   (mis. `luas_daun`, `tepi_daun`, `panjang_putik`, `warna_tangkai_sari`, seluruh `gambar_*`). Recall per kunci kanonik
   tidak bisa diukur untuk kunci tersebut dengan data ini. Daftarnya ada pada sheet `Cakupan Kanonik`.
2. **NO_MATCH dominan (49%).** Data riset dan deskripsi Kementan memuat banyak atribut agronomi/hasil (berat, umur panen,
   hasil per hektar, daya simpan) yang tidak ada di kanonik. Ini sah untuk menguji deteksi atribut baru (skenario 4A katalog
   tumbuh), tetapi metrik pemetaan sebaiknya dilaporkan terpisah untuk butir yang punya target dan yang tidak.
3. **Dataset sintetis (S01-S04) hampir semuanya ONE_TO_ONE** dan berbagi makna yang sama dalam bentuk berbeda
   (transposed, Inggris, bertingkat). Cocok untuk uji ketahanan struktur dan bahasa, tetapi bukan bukti akurasi pada data nyata.
   Laporkan hasil R dan N terpisah dari S.
4. **Label yang sama muncul di banyak dataset** (mis. `Warna daun`, `Tinggi tanaman`). Pada pembagian data/uji, pisahkan
   per dataset dan jaga kebocoran alias (lihat desain katalog tumbuh).

### Butir yang sengaja diberi penanda adjudikasi

- `kepala putik` (stigma) vs kanonik `warna tangkai putik` (style): dibuat NO_MATCH karena bagian bunganya berbeda.
- `benang sari` (stamen) tanpa penyebutan bagian: AMBIGUOUS antara `warna_tangkai_sari` dan `warna_kepala_sari`.
- `Warna kotak sari` dipetakan ke `warna_kepala_sari` (kotak sari = anther).
- Ukuran/panjang buah tanpa tahap kematangan: AMBIGUOUS antara `panjang_buah_muda` dan `panjang_buah_masak`.
- `Orientasi pedunkulus`, `Tipe berbuah`, `Corolla diameter`, `Leaf size as recorded` (satu angka, E08), ketinggian lahan sampel.
- Diameter buah/batang dianggap bukan keliling dan bukan karakteristik `batang` kanonik (NO_MATCH, keyakinan Sedang).

## 4. Cara memakai

- UI: pilih format, jumlah baris header, dan sheet sesuai tabel pada bagian 1.
- Skrip: `python eval/create_mapping_annotations.py --file <berkas> --output <keluaran> --format row-oriented --sheet "<sheet>"`
  (tambahkan opsi header sesuai dataset). Bandingkan `mapping_item_id` keluaran dengan gold di folder `gold/`.
- Untuk dua anotator manusia: salin sheet `Annotations`, kosongkan kolom kuning (`gold_status` sampai `notes`) pada salinan
  buta, jalankan protokol kampanye anotasi, lalu adjudikasi terhadap berkas gold di sini.

## 5. Yang belum ada

- **Gold klasifikasi gambar** (>=150 foto, komposisi 60/30/10 KNOWN/OTHER/UNCERTAIN) belum dibuat. Itu membutuhkan
  kumpulan foto berlabel varietas, bukan spreadsheet.
- **Nilai (value-level) gold**: anotasi di sini hanya tingkat atribut (pemetaan label). Gold untuk normalisasi nilai/satuan
  belum disusun.
- Hasil jalankan pipeline atas dataset ini belum ada (dokumen ini hanya menyiapkan input dan gold).

## 6. Metrik evaluasi

Rencana metrik inti dan skenario perbandingan ada di `../docs/RENCANA_EVALUASI.md`.

## Berkas tambahan (1 November 2026)

| Berkas | Fungsi | SHA-256 |
|---|---|---|
| `inputs/E08_zenodo_capsicum_en_variety.xlsx` | N08 dengan sel A1 diganti `Variety` (deviasi D4); berkas asli N08 ditolak parser | `6ede08a0163b26d08c094427292ea55ae1d5bca0b54783e6349c59546dee3b0a` |
| `gambar/spreadsheet_varietas_terdaftar.xlsx` | Daftar 8 varietas terdaftar untuk run foto Commons; pembantu, bukan data penelitian | `f3a3bd949a2eae4e45ac2f67aaf1617fd2565799ecb9f41d47fa439ee3c9797f` |

## Dataset berpasangan PVT: foto + spreadsheet + gold, 34 varietas terdaftar (5 November 2026)

Sumber tunggal untuk kedua modalitas: 34 dokumen **Berita Resmi PVT** (Pusat PVTPP Kementan) jenis Pendaftaran
Varietas di `dataset_eksperimen/2_input_foto/pvt_kementan_34_varietas/sumber_pdf/`. Setiap dokumen memuat nama varietas
resmi, tabel deskripsi karakter (lapisan teks), dan foto. Karena itu foto, spreadsheet, dan gold menunjuk **varietas yang
sama** dan semuanya level varietas terdaftar (memenuhi D19): 24 varietas hasil pemuliaan + 10 varietas lokal terdaftar.

| ID | Berkas | Sheet | Format | Varietas | Atribut | SHA-256 |
|---|---|---|---|---|---|---|
| P01 | `inputs/P01_pvt_hasil_pemuliaan_24.xlsx` | Deskripsi Varietas | row-oriented, header 1 baris, anchor `Varietas Cabai` | 24 hasil pemuliaan | 234 (233 + anchor) | `ecb1168bbaab7959a0abf290743fc7b4fb51a120f0796d9a146f44f8719d1cce` |
| P02 | `inputs/P02_pvt_varietas_lokal_10.xlsx` | transposed | transposed, baris `Karakter` | 10 lokal | 264 | `c430db6dacd532b648609b1e665a6aa74235d727acbbafd0a1b5448056ca4e1a` |

Label dan nilai disalin apa adanya dari lapisan teks PDF (`pdftotext -layout`), sehingga variasi aslinya terjaga: empat
gaya dokumen (format Kepmentan `: :`, format UPOV/PVT, format lokal dengan satuan di label, dan deskripsi satu paragraf),
403 label unik untuk 34 varietas, label bersinonim (`Warna buah tua` / `Warna buah matang` / `Warna kulit buah tua` /
`Warna buah tua/ matang`), satuan berbeda (cm vs mm), RHS ditulis berbeda-beda, salah ketik sumber (`antosinin`,
`meliintang`). Perubahan yang dilakukan hanya: footer dokumen elektronik dan judul bagian tanpa nilai dibuang; sub-butir
di bawah judul digabung (`Warna bunga: Kelopak Bunga`); label yang hanya beda huruf besar/kecil disatukan (parser proyek
menganggapnya duplikat); label ganda dalam satu dokumen diberi akhiran `(2)`; `Ha?1` (superskrip terbaca salah) menjadi
`Ha-1`; nama orang (pemohon, pemulia, pendeskripsi) tidak disalin. Sheet `sumber` tiap workbook mencatat No. Publikasi,
No. Pendaftaran, SHA-256 PDF, dan URL per varietas.

Gold:

| Berkas | Isi | Status |
|---|---|---|
| `gold/gold_P01_P02_pvt.csv` | Pemetaan atribut, 498 butir (P01 234, P02 264): ONE_TO_ONE 124, NO_MATCH 344, AMBIGUOUS 28, COMPOSITE 2. Mencakup 41 kunci kanonik. Format sama dengan `gold_semua_dataset.csv` + kolom `rule_source` | **Usulan AI** (`ai_single_annotator_v1`). 190 butir memakai aturan lama yang sudah diverifikasi peneliti (`lama_terverifikasi`); 308 butir dari aturan baru (`pvt_baru`). 144 butir `perlu_adjudikasi = Y` |
| `gold/kunci_sel/kunci_sel_pvt.csv` | Kunci nilai per sel (varietas × kunci kanonik) untuk atribut ONE_TO_ONE, format `kunci_sel_semua.csv`; nilai = teks dokumen resmi | Mengikuti gold atribut |
| `gambar/manifest/gold_foto_pvt_317.csv` | 317 foto: `true_variety` (dari dokumen resmi), skenario KNOWN/OTHER, `true_part`, `ada_kartu_nama`, No. Publikasi, URL | Varietas: label resmi. Bagian tanaman dan kartu: **usulan AI** dari tinjauan visual lembar kontak (`ai_visual_review_v1`), 34 foto keyakinan rendah |

Skenario registri yang disarankan untuk uji foto: jalankan foto bersama **P01** sebagai spreadsheet pendamping. 24
varietas P01 menjadi daftar terdaftar (174 foto KNOWN), 10 varietas lokal P02 tidak ada di run (143 foto OTHER); kolom
`label_kind_skenario_P01`. Bagian tanaman: BUAH 135, DAUN 59, BUNGA 50, BATANG 25 (269 dapat dinilai,
`part_dinilai = Y`), ditambah HABITUS 30, BIJI 7, TIDAK_JELAS 11 yang tidak punya kelas di kontrak `VisionResult`.

Keterbatasan: foto hanya 125–164 px (resolusi tertanam di PDF); 287 dari 317 foto memuat kartu nama varietas
(bocoran label, gunakan kondisi kartu tertutup seperti `pvt_uji_40` untuk klaim visual); gold atribut dan bagian foto
belum diverifikasi manusia; syarat penggunaan ulang foto belum diperiksa (cantumkan No. Publikasi). Keputusan pemetaan
baru yang paling perlu diperiksa: warna daun permukaan atas → `warna_daun` (bawah → NO_MATCH); `Warna tangkai daun` →
AMBIGUOUS pangkal atas/bawah; `Bulu pada buku` → `batang`; undulasi tepi daun → `tepi_daun`; `Lepuhan daun` →
`tekstur_daun`; kelopak buah (menutup/terbuka) → AMBIGUOUS `bentuk_kelopak_buah_muda|kedudukan_kelopak_bunga`;
`Sebaran Geografis` → `lokasi`.

Membuat ulang (deterministik, SHA-256 sama): `python -I data_evaluasi/skrip/buat_dataset_pvt.py` dari akar repo
(butuh `pdftotext`). Skrip: `pvt_ekstrak.py` (ekstraksi PDF), `annotations_pvt.py` (aturan pemetaan),
`anotasi_bagian_pvt.py` (anotasi bagian foto). Tes: `tests/test_pvt_dataset.py`.

### Kandidat sumber luar (belum diunduh)

Situs berikut tidak bisa diakses dari sesi cloud ini (jaringan dibatasi), jadi hanya metadata dari mesin pencari:

| Sumber | Isi | Kesesuaian |
|---|---|---|
| Kumpulan data citra telepon pintar untuk identifikasi varietas cabai merah berbasis daun (BRIN; *Data in Brief*), https://ejournal.brin.go.id/baca/article/view/7786 | 3.877 foto daun, 12 kelas varietas, kebun Balitsa | Paling relevan: varietas Indonesia, kemungkinan varietas Balitsa terdaftar. Perlu cek nama 12 varietas dan lisensi. Hanya daun, tanpa spreadsheet deskripsi |
| JNUCLS, Mendeley Data 10.17632/sbjykmmz4s.1 (RDA Korea) | 552 foto daun, 77 aksesi berkode | Perlu cek apakah kode aksesi punya nama kultivar |
| Bangladeshi Chili Dataset, https://data.mendeley.com/datasets/f6w29f8rvn | 779 foto, 7 kelas (Bari 1, Bijli, Bindu, Bombai, Cherry, F1, Red chili) | Campuran: Bari 1 varietas resmi, sisanya nama tipe/umum; kebanyakan gagal D19 |
| Indian Dried Red Chillies, https://data.mendeley.com/datasets/ghtdwrfh55/4 | 1.080 foto cabai kering, 5 kelas (Kashmiri, Byadgi, Guntur, ...) | Nama dagang/landrace dan cabai kering; kurang cocok |
