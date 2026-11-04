# Ringkasan Eksperimen CABAI-KMS (versi mudah dibaca)

Kondisi per 4 November 2026. Semua angka di sini sama dengan paper draf v11 dan memakai:
- hasil foto yang dikoreksi (19 foto yang dulu dijawab "mock" sudah dijalankan ulang dengan model sungguhan);
- gold bagian tanaman 160 foto Commons yang diisi peneliti;
- gold 12 foto Indonesia yang diisi peneliti.

Kalau cuma punya waktu 1 menit, baca **Bagian 0**. Untuk rincian teknis lengkap, lihat `docs/PANDUAN_EKSPERIMEN_LENGKAP.md`.

---

## 0. Inti dalam 1 menit

Sistem ini punya **dua pekerjaan**, dan keduanya diuji terpisah:

| Pekerjaan | Pertanyaan ujinya | Skor utama | Artinya |
|---|---|---|---|
| **A. Merapikan atribut spreadsheet** | Apakah kolom-kolom spreadsheet yang berantakan dipindahkan ke baris template yang benar? | **F1 = 0,978** (data uji baru) | Hampir semua benar. Kalau ragu, sistem memilih tidak menulis, bukan menulis salah. |
| **B. Mengenali dan menautkan foto** | Apakah foto cabai dikenali varietasnya, lalu ditautkan ke kolom varietas yang benar? | **Macro-F1 = 0,640**, tautan otomatis benar **73,6%** | Lumayan, tapi masih sering salah pada varietas mirip yang tidak terdaftar. |

Ditambah satu **skor gabungan** untuk workbook akhir (isi sel atribut + link foto sekaligus): **F1 = 0,820**.
Bagian tanaman foto (daun/buah/bunga) ditebak benar pada **95,9%** foto.

Kesimpulan paling jujur:
- Untuk atribut, sistem jauh lebih baik dari pembanding sederhana (0,978 vs 0,621 / 0,377 / 0,460), dan dari 129 yang ditulis
  otomatis, **128 benar**.
- Untuk foto, sistem jauh lebih baik daripada menebak dari nama file (0,640 vs 0,314). Tapi kalau nama file tidak membantu
  (misalnya `IMG_0061.jpg`), sekitar **1 dari 3 tautan otomatis salah**.

### Papan skor terbaru (semua metrik)

| Bagian | Metrik | Skor | Penjelasan |
|---|---|---|---|
| **Atribut** (uji baru: R02, N07, N08, N09) | F1 pemetaan, sistem penuh S4 | **0,978** [0,929; 1,000] | 6.1 |
| | Precision / Recall / Recall NULL | 1,000 / 0,958 / 1,000 | 6.1 |
| | Pembanding S1 / S2 / S2+τ / S3 | 0,621 / 0,377 / 0,460 / 1,000 | 6.1 |
| | Ditulis otomatis yang benar | 128/129 = 0,992 | 6.2 |
| | Dikirim ke review | 164 dari 293 (56%) | 6.2 |
| **Isi sel** (uji baru) | F1 posisi / F1 ketat | 0,946 / 0,591 (1,000 setelah perbaikan) | 6.3 |
| **Foto Commons** (160) | Macro-F1 status (V3) | **0,640** [0,531; 0,728] | 6.4 |
| | Macro-F1 hanya nama file (V2) | 0,314 | 6.4 |
| | Top-1 varietas (foto KNOWN) | 72/99 = 0,727 | 6.4 |
| | Recall OTHER | 30/45 = 0,667 | 6.4 |
| | Tautan otomatis benar: semua / informatif / netral / menyesatkan | 64/87 = 0,736 / 35/36 / 29/45 / 0/6 | 6.4 |
| | Bagian tanaman benar | 140/146 = 0,959 (daun 5/10) | 6.6b |
| **Foto Indonesia** (12 x 3 spreadsheet) | Status dan varietas benar | 23/36 (S01 8, S02 8, S03 7 dari 12) | 6.5 |
| | Macro-F1 (KNOWN/OTHER) / Top-1 | 0,706 / 0,773 | 6.5 |
| | Tautan otomatis benar | 15/24 = 0,625 | 6.5 |
| **Foto gabungan** (196 keputusan) | Macro-F1 / Top-1 / tautan otomatis benar | 0,632 / 0,736 / 79/111 = 0,712 | 6.5 |
| **Workbook akhir** (atribut + foto) | F1 semua run | **0,820** (Indonesia 0,872; Commons 0,677) | 6.6 |
| **Skema dinamis** | Baris baru / duplikat template / kemiripan antarpengulangan | 40 / 0 / 70-78% | 6.7 |

---

## 1. Sistemnya ngapain?

Bayangkan peneliti lapangan mengirim spreadsheet cabai yang formatnya beda-beda: ada yang varietas di baris, ada yang di
kolom, ada yang pakai bahasa Inggris, ada yang header-nya dua tingkat. Fotonya juga ditaruh campur aduk di satu folder Google
Drive.

KMS butuh semuanya dalam **satu bentuk baku**, yaitu **template kanonik 60 baris**:
- 55 baris karakter tanaman (warna daun, panjang buah, bentuk bunga, dll.),
- 1 baris lokasi,
- 4 baris foto (Gambar Daun, Batang, Buah, Bunga).

Kolom-kolomnya adalah varietas. Jadi hasil akhirnya satu tabel: **baris = karakter, kolom = varietas, sel = nilai atau link
foto**.

### Alur atribut (pekerjaan A)

```
Spreadsheet sumber
  -> cari kolom nama varietas
  -> tiap atribut sumber (mis. "Warna Buah Matang"):
       1. Nama persis sama dengan baris template?        -> langsung ketemu
       2. Kalau tidak: cari 8 baris template paling mirip (embedding / retrieval)
       3. LLM memilih satu baris, ATAU menjawab NULL ("tidak ada padanannya")
       4. Pemeriksa otomatis (verifier) mengecek jawabannya
       5. Gerbang: yakin -> DITULIS otomatis; tidak yakin / NULL -> dikirim ke REVIEW manusia
  -> nilai dirapikan (koma desimal, tanda rentang, huruf)
  -> workbook kanonik
```

### Alur foto (pekerjaan B)

```
Foto dari Drive
  -> model visi menerima: FOTO + NAMA FILE + DAFTAR VARIETAS dari spreadsheet
  -> model menjawab: KNOWN (varietas terdaftar, sebut yang mana) / OTHER (cabai lain, tidak terdaftar) / UNCERTAIN (tidak bisa ditentukan)
                     + bagian tanaman (daun/batang/buah/bunga) + tingkat yakin
  -> aturan fusi memutuskan tindakan:
       KNOWN, yakin >= 0,85, cocok dengan daftar & nama file   -> AUTO_LINK (link foto DITULIS ke workbook)
       OTHER, yakin >= 0,80                                    -> CANDIDATE (antrean varietas baru, tidak ditulis)
       selain itu (ragu / bertentangan / UNCERTAIN)            -> REVIEW manusia (tidak ditulis)
```

---

## 2. Data input (apa yang dimasukkan ke sistem)

### 2.1 Spreadsheet untuk menguji atribut: 9 workbook

| ID | Asalnya | Bentuk | Kelompok | Jumlah atribut |
|---|---|---|---|---|
| R01 | Data lapangan asli tim peneliti | varietas per baris, header 2 tingkat | Pengembangan | 14 |
| S01 | Buatan (sintetis) | varietas per kolom (transposed) | Pengembangan | 21 |
| S02 | Buatan, bahasa Inggris | varietas per baris | Pengembangan | 26 |
| S03 | Buatan, header 2 tingkat | varietas per baris | Pengembangan | 30 |
| R02 | Gabungan Zenodo + Kementan | varietas per baris | **Uji baru (held-out)** | 54 |
| N07 | SK pelepasan varietas Kementan | varietas per baris | **Uji baru** | 70 |
| N08 | Data *Capsicum* Zenodo (Brasil), Inggris | varietas per baris | **Uji baru** | 23 |
| N09 | Deskripsi varietas resmi | varietas per kolom | **Uji baru** | 80 |
| S04 | Buatan, sengaja rusak (nama varietas kosong) | - | Uji penolakan | 8 |

Total 326 atribut. Yang dinilai **299 atribut**:
- 142 punya pasangan baris di template (mis. "Leaf shape" -> `bentuk_daun`),
- 157 memang **tidak punya pasangan** (mis. "Umur panen", "Pemulia"). Untuk yang ini, jawaban benarnya NULL.

19 atribut yang ambigu (mis. "Panjang buah" tanpa keterangan muda/matang) tidak masuk skor utama, tapi dianalisis terpisah.

**Kenapa ada "pengembangan" dan "uji baru"?** Selama membangun sistem, nama-nama alternatif (alias) di template disetel
dengan melihat R01, S01-S03. Supaya adil, skor utama dihitung pada 4 workbook yang **tidak pernah dilihat** waktu
pengembangan (R02, N07, N08, N09). Mirip ujian: soal latihan tidak dipakai untuk menilai.

### 2.2 Foto

**Foto utama: 160 foto Wikimedia Commons** (lisensi dicatat), dibagi ke 8 folder Drive (F1-F8, masing-masing 20 foto).

Spreadsheet pasangannya berisi **8 varietas terdaftar**: Cabai Rawit, Jalapeno, Habanero, Cayenne, Paprika, Cabai Korea,
Serrano, Hungarian Wax.

| Jenis foto (kunci jawaban) | Jumlah | Contoh |
|---|---|---|
| KNOWN: varietasnya ada di daftar | 99 | foto Jalapeno |
| OTHER: cabai lain yang tidak terdaftar | 45 | Scotch Bonnet, Carolina Reaper, Banana Pepper |
| UNCERTAIN: varietas tidak bisa ditentukan | 16 | foto cabai campur di pasar |

Nama filenya **sengaja diatur** untuk menguji apakah sistem terlalu percaya nama file:

| Kondisi nama file | Jumlah | Contoh |
|---|---|---|
| Informatif (nama benar) | 64 | `jalapeno_buah_117.jpg` |
| Netral (tidak ada info) | 64 | `IMG_0061.jpg` |
| Menyesatkan (menyebut varietas lain yang salah) | 32 | foto Jalapeno diberi nama `habanero_...` |

**Foto tambahan: 12 foto cabai Indonesia** koleksi tim (Katokkon, Gendot, Kopay, dll.). Dipakai bersama S01, S02, S03; semua
12 foto dinilai di tiap run.

### 2.3 Template kanonik
`template_kanonik.xlsx`: 60 baris, plus 10 varietas referensi (Gendot, Kopay, Katokkon, dll.).

---

## 3. Kunci jawaban (gold): dari mana "benar"-nya?

- **Atribut:** pasangan yang benar diusulkan dengan bantuan LLM, lalu dicek satu per satu oleh peneliti. Sehari kemudian,
  peneliti menganotasi ulang 100 butir tanpa melihat kunci dan dalam urutan acak. Kecocokannya **98%** (kappa 0,97). Ini
  menunjukkan pelabelannya konsisten. Namun, ini belum penilaian pakar independen.
- **Foto Commons, varietas:** dari kategori Commons tempat foto itu diunggah (mis. kategori "Jalapeno"). Ada versi kedua hasil
  tinjauan visual AI, dipakai sebagai pembanding.
- **Foto Commons, bagian tanaman:** diisi sendiri oleh peneliti (4 Nov 2026), dengan melihat foto saja: tanpa nama file,
  label lama, atau jawaban sistem. Berkas: `data_evaluasi/gold/bagian_foto_commons/gold_bagian_commons.csv`.
- **Foto Indonesia:** diisi sendiri oleh peneliti (4 Nov 2026): varietas, bagian tanaman, dan kelayakan foto. Tiga foto yang
  varietasnya tidak diketahui peneliti diisi dengan tebakan visual AI, atas persetujuan peneliti: `C. annuum ...` = Cabai Besar,
  `p9vb...` = Gendot, daun `C. chinense dan C. annuum` = dua jenis, tidak terdaftar. Status KNOWN/OTHER per spreadsheet
  dihitung otomatis: terdaftar di spreadsheet itu = KNOWN, tidak terdaftar = OTHER. Berkas:
  `data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv`.

---

## 4. Cara uji coba

| Pengujian | Bagaimana dijalankan | Diulang |
|---|---|---|
| Atribut | Skrip "harness" di VPS yang memanggil pipeline produksi yang sama dengan website, plus 1x lewat website | 3x; hasilnya identik, dan website sama dengan harness |
| Foto Commons | Lewat website (UI), 8 run x 20 foto (1 Nov). 19 foto yang ternyata dijawab mock dijalankan ulang dengan model (4 Nov) | 1x |
| Foto Indonesia | Lewat website, bersama S01, S02, S03 (31 Okt), plus harness | 1x lewat website + 3x harness; jumlah benar sama di semua run |

Model yang dipakai: teks `gemini-3.8-flash-medium`, visi `gemini-3.8-flash-high`, embedding
`paraphrase-multilingual-MiniLM-L12-v2`.

### Pembanding (varian)

Supaya kelihatan apakah sistem memang lebih baik, ia dibandingkan dengan cara-cara yang lebih sederhana.

> **Jangan tertukar:** S1, S2, S3, S4 (satu digit) adalah **metode**. S01, S02, S03, S04 (dua digit) adalah **workbook
> sintetis** (data input). Contohnya, "S2" = metode "paling mirip", sedangkan "S02" = spreadsheet berbahasa Inggris.

| Kode | Cara kerja | Analogi |
|---|---|---|
| **S1** | Hanya nama persis sama | "Cari kata yang sama persis" |
| **S2** | Ambil baris paling mirip menurut embedding, selalu menjawab | "Pilih yang paling mirip, tidak pernah bilang tidak tahu" |
| **S2+τ** | Seperti S2, tapi menjawab NULL kalau kemiripannya kurang dari ambang (τ = 0,386) | "Pilih yang paling mirip, kecuali terlalu beda" |
| **S3** | Sistem penuh tanpa tahap pencarian: LLM langsung melihat seluruh 60 baris | "LLM membaca seluruh template" |
| **S4** | **Sistem penuh** | yang diusulkan di paper |
| **V2** | Foto: hanya dari nama file | "Tebak dari nama file" |
| **V3** | Foto: sistem penuh (foto + nama file + daftar varietas) | yang diusulkan |

---

## 5. Data output (apa yang keluar dari sistem)

Setiap run menghasilkan:

| Berkas | Isinya |
|---|---|
| `hasil_kanonik.xlsx` | Workbook template 60 baris yang sudah terisi: sel karakter dan link foto di baris Gambar |
| `pemetaan_atribut.csv` | Per atribut sumber: dipetakan ke baris mana (atau NULL), tingkat yakin, alasan model, ditulis atau ke review |
| `klasifikasi_foto.csv` | Per foto: KNOWN/OTHER/UNCERTAIN, varietas, bagian tanaman, tingkat yakin, tindakan (AUTO_LINK/CANDIDATE/REVIEW) |

Salinan semua input dan output ada di `dataset_eksperimen/`.

---

## 6. Semua skor, satu per satu

Istilah dasar yang dipakai berulang:
- **Precision**: dari yang sistem jawab/tulis, berapa persen yang benar. "Kalau menulis, seberapa bisa dipercaya?"
- **Recall**: dari yang seharusnya ketemu, berapa persen yang benar-benar ketemu. "Seberapa lengkap?"
- **F1**: gabungan precision dan recall jadi satu angka (0 = buruk, 1 = sempurna). F1 hanya tinggi kalau keduanya tinggi.
- **Angka dalam kurung [a; b]**: rentang ketidakpastian 95%. Makin sempit, makin pasti.

### 6.1 Pemetaan atribut (skor utama pekerjaan A)

Dihitung pada 4 workbook uji baru (R02, N07, N08, N09): 71 atribut yang punya pasangan dan 137 yang tidak punya pasangan.
Setiap baris tabel adalah **metode** yang dijalankan pada keempat workbook itu. Workbook sintetis S01-S03 tidak ada di
tabel ini; skornya ada di "Per workbook" di bawah (mis. workbook S02 berbahasa Inggris: S4 = 1,000).

| Varian | Precision | Recall | **F1** | Recall NULL |
|---|---|---|---|---|
| S1 nama persis | 1,000 | 0,451 | 0,621 | 1,000 |
| S2 paling mirip | 0,254 | 0,732 | 0,377 | 0,022 |
| S2+τ | 0,345 | 0,690 | 0,460 | 0,438 |
| S3 tanpa pencarian | 1,000 | 1,000 | 1,000 | 1,000 |
| **S4 sistem penuh** | **1,000** | **0,958** | **0,978** [0,929; 1,000] | **1,000** |

Cara membacanya:
- **S4 precision 1,000**: setiap kali S4 memilih baris, pilihannya benar.
- **S4 recall 0,958**: dari 71 atribut yang punya pasangan, 68 ketemu dan 3 terlewat (*Mahkota*, *Leaf shape*,
  *Mature fruit colour*). Ketiganya terlewat karena baris yang benar tidak masuk 8 kandidat, lalu LLM menjawab NULL. LLM
  tidak memilih baris yang salah.
- **Recall NULL 1,000**: dari 137 atribut yang memang tidak punya pasangan, semuanya dijawab NULL. Sistem tidak memaksakan
  pasangan.
- **S2 recall NULL 0,022**: S2 hampir tidak pernah bilang "tidak ada pasangan", jadi banyak atribut seperti "Umur panen"
  dipaksa masuk ke baris yang salah. Itu sebabnya precision-nya jatuh ke 0,254.
- **S3 = 1,000**: kalau LLM diberi seluruh 60 baris sekaligus, hasilnya malah sedikit lebih baik. Selisihnya tidak
  signifikan. Artinya, untuk template sekecil 60 baris, tahap pencarian (retrieval) belum terbukti perlu. Ini temuan yang
  diakui terbuka di paper.

**Per workbook (F1 S4):** R01 0,667 · S01 0,974 · S02 1,000 · S03 0,783 · R02 1,000 · N07 0,974 · N08 0,875 · N09 1,000.
S4 lebih tinggi dari S1, S2, dan S2+τ di **8 dari 8 workbook**. R01 hanya punya 1 atribut yang bisa dipasangkan, jadi
F1-nya kasar.

**Atribut ambigu (19 butir):** S4 menjawab NULL untuk 17. Kalau dihitung dengan aturan paling ketat, F1 S4 turun ke 0,850,
tapi tetap unggul minimal 0,32 dari semua pembanding.

### 6.2 Penulisan otomatis dan beban review

Dari 293 atribut yang diberi jawaban oleh sistem:

| | Jumlah | Keterangan |
|---|---|---|
| Ditulis otomatis | 129 | **128 benar** (99,2%). Satu salah: kolom "No" di R01 dipetakan ke Lokasi |
| Dikirim ke review | 164 (56%) | Semuanya usulan NULL. 150 memang tidak punya pasangan, 14 adalah pasangan yang terlewat |

Artinya: kesalahan sistem hampir selalu berupa **tidak menulis** (lalu ditanyakan ke manusia), bukan menulis salah. Untuk
basis data, itu jenis kesalahan yang paling aman.

### 6.3 Isi spreadsheet per sel

Skor 6.1 menilai apakah atribut dipetakan ke baris yang benar. Skor ini menilai apakah **isi sel di workbook akhir** juga
benar: nilainya tepat, dan berada di kolom varietas yang tepat.

| Cara menilai | Hasil (workbook uji baru, 342 sel) |
|---|---|
| Posisi kolom (kolom ke-1 = varietas ke-1) | precision 1,000, recall 0,898, **F1 0,946** |
| Ketat (kolom harus bernama varietas yang benar) | **F1 0,591** pada run paper |

Kenapa skor ketat rendah? Pada N07 dan R02, sistem salah mengambil kolom "Keunggulan varietas" sebagai nama varietas, karena
pembanding teksnya peka huruf besar-kecil. Bug ini sudah diperbaiki (commit `ac4f2e4`). Setelah dijalankan ulang, N07 dan R02
mendapat **F1 ketat 1,000**. Selain itu, perapian nilai mengubah 111 dari 521 sel (koma desimal, tanda rentang, huruf), dan
tidak ada yang berubah makna.

### 6.4 Foto Commons (skor utama pekerjaan B)

| Skor | Hasil | Artinya |
|---|---|---|
| **Macro-F1 status** | **0,640** [0,531; 0,728] | Seberapa tepat foto digolongkan KNOWN/OTHER/UNCERTAIN (rata-rata ketiga golongan) |
| Macro-F1 kalau hanya dari nama file (V2) | 0,314 | Pembanding. Sistem penuh jauh lebih baik (+0,326) |
| **Top-1 varietas** (foto KNOWN) | **0,727** = 72/99 | Dari 99 foto varietas terdaftar, 72 ditebak tepat varietasnya |
| Recall OTHER | 0,667 = 30/45 | Dari 45 foto varietas tak terdaftar, 30 dikenali sebagai "tidak terdaftar" |
| Foto bukan-KNOWN yang dianggap KNOWN | 19 dari 61 | Inilah sumber kesalahan utama (dipaksa ke varietas terdaftar yang mirip) |
| **Presisi AUTO_LINK** | **0,736** = 64/87 | Dari 87 link yang ditulis otomatis, 64 benar |

**Cara menghitung macro-F1.** Ini tabel hasilnya (baris = kunci jawaban, kolom = jawaban sistem):

| kunci \ sistem | KNOWN | OTHER | UNCERTAIN | total |
|---|---|---|---|---|
| KNOWN | **81** | 15 | 3 | 99 |
| OTHER | 15 | **30** | 0 | 45 |
| UNCERTAIN | 4 | 6 | **6** | 16 |

- F1 golongan KNOWN 0,814, OTHER 0,625, UNCERTAIN 0,480.
- Macro-F1 = rata-rata ketiganya = **0,640**.
- UNCERTAIN paling sulit: model jarang mau bilang "tidak tahu".

**Cara menghitung Top-1.** Dari 99 foto KNOWN:
- 72 dijawab KNOWN dengan varietas tepat (**benar**);
- 9 dijawab KNOWN tapi salah varietas (mis. Cayenne dijawab Cabai Rawit);
- 15 dijawab OTHER;
- 3 dijawab UNCERTAIN.

Hasilnya 72/99 = **0,727**.

**Tautan otomatis menurut kondisi nama file** (bagian paling penting untuk dipakai di dunia nyata):

| Nama file | Link otomatis benar | Artinya |
|---|---|---|
| Informatif | 35/36 = **97%** | Hampir selalu benar, tapi kondisi ini paling tidak realistis |
| **Netral** (`IMG_xxxx`) | 29/45 = **64%** | Kondisi paling mirip folder lapangan. Sekitar 1 dari 3 link salah |
| Menyesatkan | 0/6 | 26 dari 32 foto berhasil ditahan ke review, tapi 6 yang lolos semuanya salah |

Dari 16 link salah pada nama netral:
- 10 karena varietas tak terdaftar dipaksa masuk ke kolom yang mirip (Scotch Bonnet, Carolina Reaper -> Habanero; Banana
  Pepper -> Hungarian Wax);
- 4 karena salah memilih varietas terdaftar;
- 2 dari foto tak jelas yang tetap ditautkan.

### 6.5 Foto Indonesia (12 foto, bersama S01-S03)

| Run | Status benar | Macro-F1 (KNOWN/OTHER) | Top-1 KNOWN | Link otomatis benar |
|---|---|---|---|---|
| S01 | 8/12 | 0,778 | 0,750 | 5/8 |
| S02 | 8/12 | 0,804 | 0,750 | 6/8 |
| S03 | 7/12 | 0,556 | 0,833 | 4/8 |
| **Total** | **23/36** | **0,706** | **0,773** | **15/24 = 0,625** |

Kenapa macro-F1 di sini hanya dua golongan? Menurut gold peneliti, tidak ada foto Indonesia yang berstatus UNCERTAIN. Kalau
tetap dihitung tiga golongan, golongan UNCERTAIN otomatis bernilai 0 dan skornya turun ke 0,470 tanpa alasan yang adil.

Pola hasilnya (gold peneliti):
- Empat foto Katokkon dan foto buah Kopay selalu benar.
- Daun Gendot dan foto buah Gendot (`p9vb...`) selalu dibaca Katokkon.
- Foto cabai besar (`C. annuum ...`) ditautkan sebagai Cabai tanjung (S01, S03) atau Kopay (S02), dengan keyakinan 0,85-0,95.
- Foto daun *C. chinense* + *C. annuum* ditautkan sebagai Katokkon di S01 dan S03.
- Di S03, buah Domba yang terdaftar justru dianggap OTHER.

Sampelnya kecil (12 foto unik dipakai di 3 run), dan varietas 3 foto adalah tebakan AI, jadi buktinya lemah.

**Foto Commons + Indonesia digabung (196 keputusan):** macro-F1 0,632, Top-1 0,736, link otomatis benar 79/111 = 0,712.

### 6.6 Skor gabungan workbook akhir (atribut + foto sekaligus)

Ini skor yang menjawab: "dari semua yang ditulis sistem ke workbook akhir, seberapa benar?" Satuannya:
- 1 sel atribut = 1 unit;
- 1 link foto = 1 unit.

| | Benar | Salah tulis | Terlewat | Precision | Recall | **F1** |
|---|---|---|---|---|---|---|
| Sel atribut (S01-S03) | 212 | 0 | 44 | 1,000 | 0,828 | 0,906 |
| Link foto (Commons + Indonesia) | 75 | 36 | 46 | 0,676 | 0,620 | 0,647 |
| **Total** | **287** | **36** | **90** | **0,889** | **0,761** | **0,820** |

Hitungannya:
- precision = 287/(287+36) = 0,889;
- recall = 287/(287+90) = 0,761;
- F1 = **0,820**.

Per kelompok: run Indonesia (atribut + foto) **0,872**; run Commons (hanya foto, karena spreadsheet-nya cuma berisi nama
varietas) **0,677**.

Link foto dihitung benar hanya kalau varietasnya benar **dan** masuk ke baris Gambar yang benar menurut gold bagian
peneliti. Dari 36 link yang salah: 18 foto OTHER, 4 foto UNCERTAIN, 10 salah varietas, dan 4 salah bagian (contohnya foto
daun `habanero_buah_053.jpg` yang ditautkan ke Gambar Buah).

Hati-hati membacanya:
- Sel atribut di sini hanya dari S01-S03 (data pengembangan sintetis), karena hanya run itu yang punya atribut **dan** foto.
- Sel atribut lebih banyak (256 unit) daripada link foto (117 unit), jadi atribut yang hampir sempurna ikut mengangkat
  angka total.
- Klaim utama paper tetap memakai skor terpisah: 6.1 untuk atribut, 6.4 untuk foto.

### 6.6b Bagian tanaman foto (daun / buah / bunga / batang)

Pertanyaannya: apakah sistem menaruh foto di baris Gambar yang benar? Gold-nya diisi peneliti sendiri untuk 160 foto
Commons.

| | Hasil |
|---|---|
| Isian peneliti (bagian utama) | BUAH 128, TANAMAN_UTUH 12, DAUN 10, BUNGA 7, LAIN 3 |
| Tidak dinilai | 14 foto: 11 tanaman utuh tanpa bagian yang dominan, 3 bukan bagian tanaman |
| **Bagian ditebak benar, semua foto** | **140/146 = 95,9%** |
| Bagian benar, khusus foto yang ditautkan otomatis | 79/80 = 98,8% |
| Per bagian | BUAH 128/128, BUNGA 7/7, **DAUN 5/10** |

Jawaban sistem dihitung benar kalau sama dengan bagian utama atau bagian kedua yang diisi peneliti. Kelemahannya ada pada
foto daun: dari sepuluh foto daun, empat dibaca BUAH dan satu dibaca BUNGA. Sistem hanya bisa menjawab
DAUN, BATANG, BUAH, atau BUNGA, sesuai empat baris Gambar di template.

### 6.7 Baris template baru (skema dinamis)

Fitur tambahan: atribut yang tidak punya pasangan bisa otomatis dijadikan **baris baru** di bawah 60 baris template.
- Diuji 3 kali dengan urutan R01 -> N07 -> N09 -> R02, mulai dari database kosong.
- 84-85 atribut tanpa pasangan menjadi **40 baris baru**. Workbook berikutnya memakai ulang baris itu.
- Tidak ada baris baru yang menduplikasi baris template.
- Skor baris template tidak turun.
- Kemiripan hasil antarpengulangan 70-78%.

Statusnya: "bisa jalan" (uji kelayakan), belum metode yang tervalidasi.

---

## 7. Hal yang pernah salah dan sudah dikoreksi

| Masalah | Dampak | Perbaikan |
|---|---|---|
| **Mock diam-diam**: kalau panggilan model visi gagal, kode lama memakai jawaban tiruan (varietas ditebak dari nama file, bagian tanaman selalu DAUN) tanpa memberi tahu | 19 dari 160 foto Commons di run 1 Nov bukan jawaban model. Skor lama terlalu bagus (macro-F1 0,692, Top-1 0,758) | Kode diubah (D18): kalau model gagal, muncul error. 19 foto dijalankan ulang dengan model. Skor sekarang 0,640 / 0,727 |
| **Kolom varietas salah** di N07 dan R02 (diambil dari "Keunggulan varietas") | Nama kolom di workbook akhir salah; F1 sel ketat 0,591 | Pembanding header dibuat tidak peka huruf besar-kecil; rerun memberi 1,000 |
| **Gold bagian tanaman Commons** dulu diambil dari judul foto | 25 dari 160 foto berbeda dengan isian peneliti | Diganti isian peneliti. Skor workbook gabungan 0,838 -> 0,835 (satu link jadi salah bagian) |
| **Gold foto Indonesia** dulu disusun dengan bantuan AI dari nama berkas; hanya 10 foto per run dinilai | Skor lama: 21/30 benar, tautan otomatis 14/20 | Diganti isian peneliti (3 varietas tebakan AI yang disetujui). Semua 12 foto dinilai. Skor workbook gabungan 0,835 -> 0,820 |

Hasil atribut dan run foto Indonesia lewat website tidak terdampak mock. Di harness foto Indonesia ada 1 jawaban mock (rep1,
foto daun *C. chinense*), tapi jawaban itu salah sama seperti jawaban model di pengulangan lain, jadi hitungannya tidak berubah.

---

## 8. Batasan yang perlu jujur disampaikan

1. **Kunci jawaban dibuat peneliti sendiri** (dibantu LLM). Konsisten (kappa 0,97), tapi belum dicek pakar independen.
2. **Data kecil**: 9 workbook, satu komoditas (cabai), template 60 baris.
3. **Foto Commons adalah varietas luar negeri** sebagai pengganti; tidak membuktikan apa pun tentang varietas Indonesia.
   Foto Indonesia hanya 12 foto unik, dan varietas 3 di antaranya tebakan AI.
4. **Model visi hanya menerima nama varietas**, bukan deskripsi ciri-cirinya, sehingga varietas mirip mudah tertukar.
5. **Tidak ada penolakan otomatis untuk foto yang bukan cabai**. Foto seperti itu masuk ke review.
6. **Retrieval belum terbukti perlu** untuk template 60 baris (S3 sama baiknya).

---

## 9. Kamus istilah

| Istilah | Arti sederhana |
|---|---|
| Atribut | Satu kolom/label di spreadsheet sumber, mis. "Warna Buah Matang" |
| Template kanonik | Format baku 60 baris yang dipakai KMS |
| Pemetaan (mapping) | Memasangkan atribut sumber dengan satu baris template |
| NULL | "Atribut ini tidak punya pasangan di template" |
| Retrieval / embedding | Mencari baris template yang teksnya paling mirip secara makna |
| Reranker | LLM yang memilih satu dari kandidat hasil retrieval, atau menjawab NULL |
| Verifier | Pemeriksa otomatis berbasis aturan (bukan AI) |
| AUTO_ACCEPT / AUTO_LINK | Ditulis otomatis ke workbook |
| REVIEW | Tidak ditulis; menunggu keputusan manusia |
| CANDIDATE | Foto varietas baru; masuk antrean, tidak ditulis |
| KNOWN / OTHER / UNCERTAIN | Varietas terdaftar / cabai lain tidak terdaftar / tidak bisa ditentukan |
| Pengembangan (dev) vs uji baru (held-out) | Data yang dilihat saat membangun sistem vs data yang disimpan khusus untuk menilai |
| Gold / kunci jawaban | Jawaban benar yang dipakai untuk menilai sistem |
| Precision / Recall / F1 | Lihat awal Bagian 6 |
| Macro-F1 | F1 dihitung per golongan, lalu dirata-rata, supaya golongan kecil (UNCERTAIN) tetap dihitung adil |
| Top-1 | Jawaban pertama model langsung tepat (tidak ada kesempatan kedua) |
| Mock | Jawaban tiruan untuk pengujian kode, bukan jawaban model sungguhan |

---

## 10. Di mana berkasnya

| Yang dicari | Lokasi |
|---|---|
| Paper terbaru | `docs/paper/paper_ieee_draft_v11.pdf` |
| Rincian teknis lengkap | `docs/PANDUAN_EKSPERIMEN_LENGKAP.md` |
| Semua input dan output sistem | `dataset_eksperimen/` (baca `KETERANGAN_DATA.txt`) |
| Hasil foto yang sudah dikoreksi | `dataset_eksperimen/4_hasil_sistem/H_koreksi_foto_commons_D18/` |
| Angka atribut dan foto | `data_evaluasi/hasil_eksperimen/analisis_paper.md` |
| Skor gabungan workbook | `data_evaluasi/hasil_eksperimen/workbook_gabungan/hasil_skor.md` |
| Skor foto Indonesia | `data_evaluasi/hasil_eksperimen/foto_indonesia/hasil_skor.md` |
| Skor bagian tanaman | `data_evaluasi/hasil_eksperimen/bagian_foto/hasil_skor.md` |
| Gold bagian tanaman Commons | `data_evaluasi/gold/bagian_foto_commons/gold_bagian_commons.csv` |
| Gold foto Indonesia | `data_evaluasi/gambar_id/gold_peneliti/gold_kombinasi_peneliti.csv` |
| Skor isi sel | `data_evaluasi/hasil_eksperimen/akurasi_sel/akurasi_sel.md` |
