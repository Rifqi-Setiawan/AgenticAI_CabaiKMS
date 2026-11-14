# Ringkasan Eksperimen CABAI-KMS (versi mudah dibaca)

Kondisi per **12 November 2026** (visi dua tahap D24). Angka di sini memakai sistem dan data terbaru:
- data cabai sudah dibersihkan sampai **level varietas/kultivar** (D19): nama spesies, jenis umum, nama tipe, Gendot, Domba,
  Bhut Jolokia, dan GRIN Poblano dikeluarkan;
- model embedding **BAAI/bge-m3** (D22), menggantikan MiniLM;
- model visi menerima **deskripsi morfologi varietas** dari spreadsheet run, bukan hanya nama (D20);
- uji **nama file berpasangan** (D23): foto yang sama diberi nama berkas berbeda;
- **visi dua tahap** (D24): model visi **tidak lagi menerima nama berkas**; nama berkas dicocokkan oleh kode lalu dibandingkan
  dengan jawaban visual di tahap fusi. Semua angka foto di bawah memakai sistem ini; angka D23 (7 Nov) ditulis sebagai
  pembanding "lama".

Angka di draf paper v11 (4 Nov) masih memakai data dan sistem lama; lihat **Bagian 11**.
Kalau cuma punya waktu 1 menit, baca **Bagian 0**. Rincian teknis: `docs/PANDUAN_EKSPERIMEN_LENGKAP.md`.

---

## 0. Inti dalam 1 menit

Sistem ini punya **dua pekerjaan**, dan keduanya diuji terpisah:

| Pekerjaan | Pertanyaan ujinya | Skor utama | Artinya |
|---|---|---|---|
| **A. Merapikan atribut spreadsheet** | Apakah atribut spreadsheet dipindahkan ke baris template yang benar? | **F1 = 1,000** (data uji baru) | Semua benar di semua workbook. Tidak ada satu pun yang ditulis salah. |
| **B. Mengenali dan menautkan foto** | Apakah foto dikenali varietasnya, lalu ditautkan ke kolom varietas yang benar? | Lihat tabel di bawah | Bagus kalau varietasnya mudah dibedakan dari tampilan. Lemah untuk varietas Indonesia yang mirip; nama berkas tidak lagi bisa "menolong" atau "menyesatkan" model. |

Kesimpulan paling jujur:
- **Atribut:** setelah embedding diganti ke bge-m3, sistem penuh (S4) mendapat F1 1,000 di semua 7 workbook, dan isi sel
  di workbook akhir juga 1,000. Pembanding sederhana jauh di bawah (0,621 / 0,420).
- **Foto:** sampai D23, keputusan varietas pada foto PVT kartu tertutup datang dari nama berkas (model ikut nama berkas
  yang salah pada 30 dari 40 foto). Setelah D24 model tidak melihat nama berkas: ikut nama salah tinggal **2/40**, konflik
  tertangkap **7/40** (dulu 0), dan tautan otomatis salah di set berpasangan turun **17 → 8 dari 120**. Harganya, angka
  "benar" yang dulu tertolong nama berkas ikut hilang: kemampuan visual sebenarnya pada foto PVT kartu tertutup hanya
  **4 dari 19** foto KNOWN. Ini batasan utama sistem sekarang.

### Papan skor terbaru (semua metrik)

| Bagian | Metrik | Skor | Penjelasan |
|---|---|---|---|
| **Retrieval** (tanpa LLM, 109 butir semantik) | Hit@1 / Hit@8 / **MRR** | 0,826 / 1,000 / **0,883** (MiniLM: 0,376 / 0,789 / 0,517) | 6.1 |
| **Atribut** (uji baru: R02, N07, N08, N09) | F1 pemetaan, sistem penuh S4 | **1,000** [1,000; 1,000] (MiniLM: 0,978) | 6.2 |
| | Precision / Recall / Recall NULL | 1,000 / 1,000 / 1,000 | 6.2 |
| | Pembanding S1 / S2 | 0,621 / 0,420 | 6.2 |
| **Atribut** (pengembangan: S01-S03) | F1 S4 | 1,000 (MiniLM: 0,915) | 6.2 |
| | Ditulis otomatis benar / salah | 141 / 0 | 6.3 |
| | Dikirim ke review | 139 dari 285 (49%), semuanya usulan NULL | 6.3 |
| **Isi sel** (ketat) | Uji baru / pengembangan | 216/216 = **1,000** / 112/112 = **1,000** | 6.4 |
| **Foto Commons** (35, registri 1 varietas) | Status benar / tautan otomatis benar | 32,67 ± 1,15 (32-34) / 5/6, 7/8, 5/6 (D23: 35/35 / 7/7) | 6.5 |
| **Foto Indonesia** (6 x 3 spreadsheet) | Top-1 / tautan otomatis benar / bagian benar | 0,750 / 12/13 / 18/18, sama di 3 ulangan (D23: 0,812 / 12/12 / 15/18) | 6.6 |
| **Foto PVT** (40, registri 24 varietas P01) | Top-1, kartu terlihat / tertutup | 0,579 ± 0,053 / **0,175 ± 0,030** (D23: 0,632 / 0,211) | 6.7 |
| | Tautan otomatis benar, kartu terlihat / tertutup | 8/13, 9/13, 7/11 / **2/6, 1/4, 4/7** (D23: 12/19 / 3/8) | 6.7 |
| **Nama file berpasangan** (PVT kartu tertutup) | Nama salah tertangkap sebagai konflik (REVIEW_MISMATCH) | **7/40** di 3 ulangan (D23: 0/40) | 6.8 |
| | Model ikut varietas di nama berkas / tautan salah (nama salah) | **2/40 / 2** di 3 ulangan (D23: 30/40 / 12) | 6.8 |
| | Tautan otomatis salah, semua 120 keputusan | **7,67 ± 0,58** (7-8; D23: 17/120) | 6.8 |
| **Workbook akhir** (atribut + foto) | F1 Indonesia S01-S03 | **0,980** di 3 ulangan (D23: 0,960) | 6.9 |
| **Skema dinamis** | Baris baru / duplikat template / kemiripan antarpengulangan | 40 / 0 / 70-78% (data lama) | 6.10 |

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
       2. Kalau tidak: cari 8 baris template paling mirip (embedding bge-m3 / retrieval)
       3. LLM memilih satu baris, ATAU menjawab NULL ("tidak ada padanannya")
       4. Pemeriksa otomatis (verifier) mengecek jawabannya
       5. Gerbang: yakin -> DITULIS otomatis; tidak yakin / NULL -> dikirim ke REVIEW manusia
  -> nilai dirapikan (koma desimal, tanda rentang, huruf)
  -> workbook kanonik
```

### Alur foto (pekerjaan B)

```
Foto dari Drive
  -> tahap 1, model visi menerima: FOTO + DAFTAR VARIETAS + DESKRIPSI MORFOLOGI varietas dari spreadsheet run
     (TANPA nama file dan caption, D24)
  -> model menjawab: KNOWN (varietas terdaftar, sebut yang mana) / OTHER (cabai lain, tidak terdaftar) / UNCERTAIN (tidak bisa ditentukan)
                     + bagian tanaman (daun/batang/buah/bunga) + tingkat yakin
  -> tahap 2, kode (bukan AI) mencocokkan nama file ke daftar varietas
  -> aturan fusi memutuskan tindakan:
       nama file menyebut varietas terdaftar yang BERBEDA dari jawaban visual -> REVIEW_MISMATCH (tidak ditulis)
       KNOWN, yakin >= 0,85 (atau >= 0,60 bila sama dengan nama file)         -> AUTO_LINK (link foto DITULIS ke workbook)
       OTHER, yakin >= 0,80                                                  -> CANDIDATE (antrean varietas baru, tidak ditulis)
       selain itu (ragu / UNCERTAIN)                                         -> REVIEW_UNCERTAIN (tidak ditulis)
  ("Rikub 1" dan "Rikub 2" dihitung varietas berbeda. Mode lama single_call, nama file masuk prompt, tersimpan sebagai pembanding.)
```

---

## 2. Data input (apa yang dimasukkan ke sistem)

Semua data cabai sekarang sampai **level varietas atau kultivar** (D19): varietas terdaftar Kementan, varietas lokal
terdaftar (Katokkon, Kopay), atau kultivar bernama (mis. 'Hungarian Wax', 'Cheongyang', Tabasco). Yang dikeluarkan tidak
dihapus, tetapi dipindah ke folder arsip `_dikeluarkan_bukan_varietas/` (rincian: `data_evaluasi/KLASIFIKASI_LEVEL_VARIETAS.md`).

### 2.1 Spreadsheet untuk menguji atribut

| ID | Asalnya | Bentuk | Kelompok | Varietas | Atribut |
|---|---|---|---|---|---|
| S01 | Buatan (sintetis) | varietas per kolom (transposed) | Pengembangan | Kopay, Katokkon | 21 |
| S02 | Buatan, bahasa Inggris | varietas per baris | Pengembangan | Kopay, Katokkon | 26 |
| S03 | Buatan, header 2 tingkat | varietas per baris | Pengembangan | Katokkon | 30 |
| R02 | Gabungan Zenodo + Kementan | varietas per baris | **Uji baru (held-out)** | 6 varietas terdaftar | 54 |
| N07 | SK pelepasan varietas Kementan | varietas per baris | **Uji baru** | Biocalya Agrihorti, ENNO009, Arisa IPB | 70 |
| N08 | Data *Capsicum* Zenodo (Brasil), Inggris | varietas per baris | **Uji baru** | Tabasco, Etna, Pirâmide | 23 |
| N09 | Deskripsi varietas resmi | varietas per kolom | **Uji baru** | 6 varietas terdaftar | 80 |
| S04 | Buatan, sengaja rusak (nama varietas kosong) | - | Uji penolakan | - | 8 |
| P01 | Berita Resmi PVT, 24 varietas hasil pemuliaan | varietas per baris | Pasangan foto PVT (gold terverifikasi) | 24 | 234 |

R01 (data lapangan) dikeluarkan karena kolom Jenis Cabai hanya berisi spesies. Yang dinilai pada skor utama: 4 workbook uji
baru (71 atribut berpasangan, 137 tanpa pasangan) dan 3 workbook pengembangan (70 berpasangan, 7 tanpa pasangan).
19 atribut ambigu (mis. "Panjang buah" tanpa keterangan muda/matang) tidak masuk skor utama.

**Kenapa ada "pengembangan" dan "uji baru"?** Selama membangun sistem, alias baris template disetel dengan melihat S01-S03.
Supaya adil, skor utama dihitung pada workbook yang **tidak pernah dilihat** waktu pengembangan (R02, N07, N08, N09).

### 2.2 Foto

| Set | Jumlah | Daftar varietas (registri) | KNOWN / OTHER | Nama berkas |
|---|---|---|---|---|
| Commons (Wikimedia, luar negeri) | 35 | Hungarian Wax | 7 / 28 | informatif 15, netral 16, menyesatkan 4 |
| Indonesia (koleksi peneliti) | 6 foto x S01, S02, S03 | varietas spreadsheet run | 16 / 2 keputusan | semua menyebut varietas |
| PVT uji 40 (Berita Resmi PVT, Indonesia) | 40 x 2 kondisi kartu nama | 24 varietas P01 | 19 / 21 | netral (`IMG_41xx`) |
| Nama file berpasangan (D23) | 40 PVT x 3 nama + 6 Indonesia x nama netral | sama dengan di atas | sama | netral / benar / salah terdaftar |

Kondisi nama file:

| Kondisi | Arti | Contoh |
|---|---|---|
| Netral | tidak ada info varietas | `IMG_0061.jpg` |
| Benar / informatif | nama varietas foto itu sendiri | `turima_2_37.webp` |
| Salah terdaftar / menyesatkan | nama varietas terdaftar **lain** | foto Tabia Sala 1 diberi nama `tabia_sala_2_ipb_41.webp` |

Foto PVT berasal dari dokumen resmi pendaftaran varietas, jadi label varietasnya resmi. Resolusinya kecil (125-164 px), dan
38 dari 40 foto memuat kartu bertuliskan nama varietas. Karena itu klaim visual memakai versi **kartu tertutup**.

### 2.3 Template kanonik
`template_kanonik.xlsx`: 60 baris karakter.

---

## 3. Kunci jawaban (gold): dari mana "benar"-nya?

- **Atribut (S01-S03, R02, N07-N09):** diverifikasi langsung oleh penulis, butir per butir. Penulis juga menganotasi ulang
  100 butir tanpa melihat kunci; kecocokannya **98%** (kappa 0,97). Konsisten, tetapi belum penilaian pakar independen.
- **Atribut P01 (PVT, 234 butir):** diverifikasi langsung oleh penulis, butir per butir. Atribut P02 (varietas lokal,
  264 butir) belum diverifikasi dan tidak dipakai di skor utama.
- **Isi sel:** dibangun otomatis dari gold atribut + nilai mentah sumber (`akurasi_sel.py`).
- **Foto Commons:** varietas dari kategori Commons (kurasi komunitas); 5 foto dinaikkan labelnya ke nama kultivar (D19);
  bagian tanaman diisi peneliti. Tiga foto bernama `cabai-rawit_…`, `serrano_…`, `habanero_…` diubah tindakan harapannya ke
  CANDIDATE (D23), karena nama itu tidak lagi menunjuk varietas terdaftar.
- **Foto Indonesia:** diisi peneliti (varietas, bagian tanaman). Status KNOWN/OTHER per spreadsheet dihitung otomatis.
- **Foto PVT:** varietas dari dokumen resmi; bagian tanaman, kartu nama, dan kelayakan foto diverifikasi penulis. Sel tujuan dan tindakan yang benar diturunkan dengan aturan
  D21 dan D23.

---

## 4. Cara uji coba

| Pengujian | Bagaimana dijalankan | Diulang |
|---|---|---|
| Retrieval | `banding_embedding.py`: parser dan query sama dengan pipeline, tanpa LLM | sekali (deterministik) |
| Atribut | Harness VPS (`harness_vps.py`) yang memanggil `run_pipeline_ui()`, fungsi yang sama dengan tombol di website; skema dinamis mati; tanpa Commit ke KMS | **3x**; keputusan identik di ketiganya |
| Foto | `uji_visi_commons_vps.py --mode two_stage`: langkah node visi produksi (registri, deskripsi, sinyal nama file, fusi) dengan modul produksi; foto dibaca dari disk, tanpa tulis KMS; input dan varietas DB dikunci sama dengan run 7 Nov | 1x (12 Nov, 271 foto, 0 gagal); pembanding D23 1x (7 Nov) |

Model: teks `ag/gemini-3.8-flash-medium`, visi `ag/gemini-3.8-flash-high` (lewat gateway 9Router), embedding `BAAI/bge-m3`.
Semua panggilan model sungguhan; kalau provider gagal, hasilnya tercatat FAILED, tidak diganti jawaban tiruan (D18).
Jumlah baris semua tabel KMS sama sebelum dan sesudah run atribut (dibuktikan dengan `kms_sebelum.json` dan `kms_sesudah.json`).

**Catatan validitas:** run ini memakai harness, bukan klik di website. Atribut melewati fungsi pipeline yang sama dengan
website. Foto menyusun ulang langkah node visi dengan modul produksi, tetapi tanpa unduhan Drive dan tanpa penyimpanan ke KMS.
Uji paritas lewat jalur produksi penuh belum dijalankan.

### Pembanding (varian)

> **Jangan tertukar:** S1, S2, S3, S4 (satu digit) adalah **metode**. S01, S02, S03, S04 (dua digit) adalah **workbook
> sintetis** (data input).

| Kode | Cara kerja | Analogi |
|---|---|---|
| **S1** | Hanya nama persis sama | "Cari kata yang sama persis" |
| **S2** | Ambil baris paling mirip menurut embedding, selalu menjawab | "Pilih yang paling mirip, tidak pernah bilang tidak tahu" |
| **S2+τ** | Seperti S2, tapi NULL kalau kemiripan di bawah ambang | dihitung di data lama saja |
| **S3** | LLM langsung melihat seluruh 60 baris tanpa retrieval | dihitung di data lama saja |
| **S4** | **Sistem penuh** | yang diusulkan di paper |

---

## 5. Data output (apa yang keluar dari sistem)

| Berkas | Isinya |
|---|---|
| `hasil_kanonik.xlsx` | Workbook template 60 baris yang sudah terisi: sel karakter dan link foto di baris Gambar |
| `pemetaan_atribut.csv` | Per atribut sumber: dipetakan ke baris mana (atau NULL), tingkat yakin, alasan model, ditulis atau ke review |
| `klasifikasi_foto.csv` | Per foto: KNOWN/OTHER/UNCERTAIN, varietas, bagian tanaman, tingkat yakin, tindakan |

Salinan semua input dan output ada di `dataset_eksperimen/` (baca `KETERANGAN_DATA.txt`). Run terbaru:
`4_hasil_sistem/I_atribut_bge-m3_39f4213` (atribut) dan `L_visi_dua_tahap_D24` (foto). Run foto D23 sebagai pembanding:
`J_foto_ulang_D20_bge-m3`, `K_nama_file_berpasangan`.

---

## 6. Semua skor, satu per satu

Istilah dasar:
- **Precision**: dari yang sistem jawab/tulis, berapa persen yang benar. "Kalau menulis, seberapa bisa dipercaya?"
- **Recall**: dari yang seharusnya ketemu, berapa persen yang ketemu. "Seberapa lengkap?"
- **F1**: gabungan precision dan recall (0 = buruk, 1 = sempurna). Hanya tinggi kalau keduanya tinggi.
- **Angka dalam kurung [a; b]**: rentang ketidakpastian 95%. Makin sempit, makin pasti.

### 6.1 Retrieval (tahap pencarian kandidat, sebelum LLM)

Pertanyaannya: apakah baris template yang benar ikut masuk kandidat yang dikirim ke LLM? Kalau tidak masuk, LLM tidak mungkin
memilihnya. Diukur pada butir yang tidak selesai lewat nama persis (butir semantik).

- **Hit@k**: baris yang benar ada di k kandidat teratas. Hit@8 penting karena reranker melihat 8 kandidat.
- **MRR (Mean Reciprocal Rank)**: rata-rata 1/peringkat baris yang benar. 1,0 = selalu peringkat pertama; 0,5 = rata-rata
  peringkat kedua.

| Model | Hit@1 | Hit@8 | **MRR** | Gold PVT P01+P02 (Hit@1 / Hit@8 / MRR) |
|---|---|---|---|---|
| MiniLM-L12 (lama) | 0,376 | 0,789 | 0,517 | 0,344 / 0,771 / 0,486 |
| mpnet-base | 0,468 | 0,908 | 0,622 | 0,427 / 0,750 / 0,540 |
| BM25 (kata saja) | 0,578 | 0,872 | 0,682 | 0,635 / 0,927 / 0,733 |
| Harrier-OSS 270M | 0,642 | 0,908 | 0,742 | 0,604 / 0,823 / 0,680 |
| multilingual-e5-base | 0,743 | 0,945 | 0,816 | 0,698 / 0,875 / 0,752 |
| Qwen3-Embedding-0.6B | 0,752 | 0,963 | 0,825 | 0,677 / 0,833 / 0,730 |
| Harrier-OSS 0.6B | 0,752 | 0,945 | 0,826 | 0,594 / 0,823 / 0,681 |
| **bge-m3 (dipakai sekarang)** | **0,826** | **1,000** | **0,883** | 0,688 / 0,927 / 0,771 |

Gold terverifikasi, 109 butir. Kolom PVT: 96 butir (P01 terverifikasi 42, P02 belum diverifikasi 54); P01 saja:
bge-m3 0,714 / 0,905 / 0,776, MiniLM 0,381 / 0,762 / 0,519. Selisih Hit@1 bge-m3 vs MiniLM: +0,450 [+0,358; +0,541]. Gabungan BM25 + dense (RRF) dan
instruksi tugas tidak memperbaiki model terbaik. Berkas: `hasil_eksperimen/hasil_retrieval/banding_embedding/`.

### 6.2 Pemetaan atribut (skor utama pekerjaan A)

| Himpunan | Varian | Precision | Recall | **F1** | Recall NULL |
|---|---|---|---|---|---|
| Uji baru (R02, N07, N08, N09; 71 / 137) | S1 nama persis | 1,000 | 0,451 | 0,621 | 1,000 |
| | S2 paling mirip | 0,283 | 0,817 | 0,420 | 0,022 |
| | **S4 sistem penuh** | **1,000** | **1,000** | **1,000** | **1,000** |
| Pengembangan (S01-S03; 70 / 7) | S1 | 1,000 | 0,086 | 0,158 | 1,000 |
| | S2 | 0,800 | 0,857 | 0,828 | 0,286 |
| | **S4** | **1,000** | **1,000** | **1,000** | **1,000** |

**Per workbook (F1 S4, bge-m3 | MiniLM):** R02 1,000 | 1,000 · N07 1,000 | 0,974 · N08 1,000 | 0,875 · N09 1,000 | 1,000 ·
S01 1,000 | 0,974 · S02 1,000 | 1,000 · S03 1,000 | 0,783.

**Dibanding MiniLM (uji berpasangan, rep1, butir yang sama):**

| Himpunan | Selisih F1 S4 | CI 95% | p |
|---|---|---|---|
| Uji baru | +0,022 | +0,000; +0,050 | 0,095 |
| Uji baru, input identik (R02, N07, N09) | +0,008 | +0,000; +0,027 | 0,735 |
| Pengembangan | **+0,085** | +0,038; +0,140 | <0,001 |

Cara membacanya:
- **14 butir berubah, semuanya dari NULL menjadi benar.** Dengan MiniLM, baris yang benar tidak masuk 8 kandidat (contoh:
  *Mahkota*, *Leaf shape*, *Mature fruit colour*), lalu LLM menjawab NULL. Dengan bge-m3, baris itu masuk kandidat dan dipilih
  benar. Tidak ada butir yang memburuk.
- **Recall NULL 1,000**: dari 137 atribut tanpa pasangan, semuanya dijawab NULL. Sistem tidak memaksakan pasangan.
- **Klaim paling bersih ada di R02, N07, N09**, karena isinya identik di run lama dan run baru. Di sana MiniLM sudah hampir
  sempurna, jadi kenaikannya kecil dan tidak signifikan. Kenaikan besar ada di data pengembangan, yang dulu dipakai menyetel
  alias dan isinya berubah karena D19.
- Keputusan identik di tiga pengulangan; yang bervariasi hanya nilai yakin.

Berkas: `hasil_eksperimen/skor_atribut_e2e_bge-m3/skor_atribut_e2e.md`.

### 6.3 Penulisan otomatis dan beban review

| Himpunan | Butir | Ditulis otomatis benar | Ditulis otomatis salah | Ke review (usulan NULL) |
|---|---|---|---|---|
| Uji baru | 208 | 71 (MiniLM 68) | 0 | 134 (MiniLM 137) |
| Pengembangan | 77 | 70 (MiniLM 59) | 0 | 5 (MiniLM 16) |

Tidak ada yang ditulis salah. Semua yang tidak ditulis dikirim ke manusia sebagai usulan NULL, dan karena recall 1,000,
semua butir yang dikirim ke review itu memang atribut tanpa pasangan. Sisa 3 + 2 butir tidak dihasilkan sebagai baris
pemetaan (dihitung NULL). Untuk basis data, ini jenis perilaku paling aman.

### 6.4 Isi spreadsheet per sel

Skor 6.2 menilai apakah atribut dipetakan ke baris yang benar. Skor ini menilai **isi sel di workbook akhir**: nilainya tepat
dan berada di kolom varietas yang benar (mode ketat: kolom dicocokkan lewat nama varietas).

| Workbook | Kolom varietas benar | Sel harapan | Benar | Salah tulis | Terlewat | F1 |
|---|---|---|---|---|---|---|
| R02 | 6/6 | 79 | 79 | 0 | 0 | 1,000 |
| N07 | 3/3 | 37 | 37 | 0 | 0 | 1,000 |
| N08 | 3/3 | 27 | 27 | 0 | 0 | 1,000 |
| N09 | 6/6 | 73 | 73 | 0 | 0 | 1,000 |
| S01 / S02 / S03 | 2/2 / 2/2 / 1/1 | 40 / 44 / 28 | semua | 0 | 0 | 1,000 |

Perapian nilai mengubah 83 dari 328 sel (koma desimal, tanda rentang, huruf), dan tidak ada yang berubah makna.

### 6.5 Foto Commons (35 foto, registri Hungarian Wax)

| Skor | D24 (12 Nov) | D23 (7 Nov) |
|---|---|---|
| Status benar | 32/35 | 35/35 |
| Top-1 varietas (7 foto KNOWN) | 5/7 | 7/7 |
| Recall OTHER | 27/28 | 28/28 |
| Tautan otomatis benar (informatif / netral) | 5/6 (2/3 / 3/3) | 7/7 (3/3 / 4/4) |
| Bagian tanaman benar | 31/32 | 31/32 |
| Tindakan sesuai gold | 32/35 | 35/35 |

Tiga foto berubah: `hungarian-wax_buah_081.jpg` dulu tertaut karena namanya, sekarang dijawab OTHER sehingga bertentangan
dengan nama file (REVIEW_MISMATCH); `IMG_0087.jpg` menjadi UNCERTAIN; `cayenne_buah_080.jpg` salah tertaut ke Hungarian Wax
(yakin 0,85, tepat di ambang). **Hati-hati:** setelah D19 hanya 7 foto yang terdaftar, semuanya Hungarian Wax. Set ini data
pendukung, bukan bukti kuat.

### 6.6 Foto Indonesia (6 foto x spreadsheet S01, S02, S03)

| Run | Status benar | Tautan otomatis benar | Bagian benar |
|---|---|---|---|
| S01 (Kopay, Katokkon) | 4/6 | 4/4 | 6/6 |
| S02 (Kopay, Katokkon) | 4/6 | 4/4 | 6/6 |
| S03 (Katokkon) | 5/6 | 4/5 | 6/6 |
| **Total D24** | **13/18** | **12/13** | **18/18** |
| Total D23 (pembanding) | 15/18 | 12/12 | 15/18 |

Top-1 foto KNOWN 12/16 = 0,750 (D23 0,812); recall OTHER 1/2. Contoh perubahan: foto bernama salah eja
`cabai katokon - ...` dulu dijawab OTHER karena namanya tidak cocok; sekarang dikenali Katokkon dari tampilan (AUTO_LINK
benar). Foto `cabai kopay.webp` dulu tertaut karena namanya; sekarang model tidak yakin itu Kopay sehingga masuk
REVIEW_MISMATCH (aman, tapi tidak tertaut). Sampel kecil (6 foto unik, 2 varietas yang bentuk buahnya sangat berbeda).

### 6.7 Foto PVT (40 foto, registri dan deskripsi 24 varietas P01)

| Kondisi | Status benar | Top-1 KNOWN | Recall OTHER | Non-KNOWN dipaksa KNOWN | Tautan otomatis benar | Tindakan sesuai gold |
|---|---|---|---|---|---|---|
| Kartu nama terlihat, D24 | 25/40 | 11/19 = 0,579 | 14/21 | 2/21 | 8/13 | 25/40 |
| Kartu nama terlihat, D23 | 27/40 | 12/19 = 0,632 | 15/21 | 2/21 | 12/19 | 30/40 |
| **Kartu nama tertutup, D24** | **3/40** | **3/19 = 0,158** | 0/21 | 1/21 | **2/6** | 9/40 |
| Kartu nama tertutup, D23 | 4/40 | 4/19 = 0,211 | 0/21 | 2/21 | 3/8 | 11/40 |

Dengan kartu nama terlihat, model membaca tulisan di kartu. Dengan kartu tertutup, varietas hampir tidak dikenali dari foto
125 px, walaupun deskripsi morfologi P01 sudah dikirim. Sistem biasanya menahan keputusan (34 dari 40 ke REVIEW_UNCERTAIN),
tetapi **4 dari 6 tautan otomatis salah**. Selisih D24 vs D23 di set ini ada di dalam CI 95% (nama berkas set ini netral,
jadi perubahannya berasal dari variasi model antar-run).

**Tiga ulangan D24 (13-14 Nov 2026).** Input, registri, deskripsi, dan skrip skor sama; foto yang gagal karena galat
provider dijalankan ulang sampai berhasil (akhirnya 0 gagal). Rerata ± SB antar-ulangan (variasi model, bukan
ketidakpastian sampel); D23 hanya satu run.

| Metrik | Ulangan 1 / 2 / 3 | Rerata ± SB | D23 |
|---|---|---|---|
| Commons: status benar (dari 35) | 32 / 34 / 32 | 32,67 ± 1,15 | 35 |
| Commons: AUTO_LINK benar / total | 5/6, 7/8, 5/6 | - | 7/7 |
| Indonesia S01-S03: Top-1 / AUTO_LINK benar / bagian | sama di 3 ulangan: 0,750 / 12/13 / 18/18 | - | 0,812 / 12/12 / 15/18 |
| PVT kartu terlihat: Top-1 | 0,579 / 0,632 / 0,526 | 0,579 ± 0,053 | 0,632 |
| PVT kartu terlihat: AUTO_LINK benar / total | 8/13, 9/13, 7/11 | - | 12/19 |
| **PVT kartu tertutup: Top-1** | 0,158 / 0,158 / 0,211 | **0,175 ± 0,030** | 0,211 |
| PVT kartu tertutup: AUTO_LINK benar / total | 2/6, 1/4, 4/7 | - | 3/8 |
| PVT nama salah: ikut nama berkas / REVIEW_MISMATCH (dari 40) | 2, 7 di semua ulangan | - | 30, 0 |
| PVT berpasangan: tindakan sesuai gold (dari 120) | 33 / 32 / 32 | 32,33 ± 0,58 | 48 |
| PVT berpasangan: AUTO_LINK salah (dari 120) | 8 / 7 / 8 | 7,67 ± 0,58 | 17 |
| Workbook gabungan Indonesia F1 | 0,980 / 0,980 / 0,980 | 0,980 ± 0,000 | 0,960 |
| Workbook P01 + PVT kartu terlihat / tertutup F1 | 0,947-0,949 / 0,940-0,944 | 0,947 / 0,941 | 0,950 / 0,940 |

Keputusan (status, varietas, tindakan) sama di ketiga ulangan pada 112/133 foto ulang (84,2%) dan 136/156 keputusan
nama berkas berpasangan (87,2%). Kesimpulan nama berkas stabil; tabel di atas dan 6.8 memakai ulangan 1. Rekap: `hasil_eksperimen/foto_two_stage_2026-11-12/rekap_ulangan/rekap_ulangan.md`.

### 6.8 Nama file berpasangan (D23 → D24): foto sama, nama berkas berbeda

Foto yang **sama persis** diuji dengan tiga nama berkas, jadi perbedaan hasil hanya disebabkan nama berkas. Set utama: 40
foto PVT kartu tertutup, registri 24 varietas P01. Format sel: **D24** (D23).

| Foto | Nama berkas | Jawaban yang benar | Tindakan sesuai gold | Status/varietas benar | Tautan salah | Ikut nama berkas |
|---|---|---|---|---|---|---|
| KNOWN (19) | netral | AUTO_LINK benar atau REVIEW | 16/19 (16/19) | 4/19 (4/19) | 3 (3) | - |
| | benar | AUTO_LINK | 4/19 (12/19) | 3/19 (16/19) | 0 (0) | - |
| | salah terdaftar | REVIEW_MISMATCH | **6/19** (0/19) | 3/19 (1/19) | **2** (7) | **2/19** (16/19) |
| OTHER (21) | netral (kasus 1) | CANDIDATE | 3/21 (3/21) | 0/21 (0/21) | 1 (2) | - |
| | benar tapi tidak terdaftar (kasus 2) | CANDIDATE | 3/21 (17/21) | 0/21 (19/21) | 2 (0) | - |
| | salah terdaftar | REVIEW_MISMATCH | **1/21** (0/21) | 0/21 (0/21) | **0** (5) | **0/21** (14/21) |
| **Total 120** | | | **33** (48) | | **8** (17) | |

**Ablasi** (jawaban visual D24 yang sama, digabung dengan aturan fusi lama; `ablasi_fusi_m2.py`): tindakan sesuai gold
29/120, tautan salah 12/120. Jadi dari 17 → 8 tautan salah, 5 hilang karena model buta nama berkas dan 4 karena aturan fusi
baru (kontradiksi tertangkap walau yakin rendah; "Rikub 1" ≠ "Rikub 2").

Cara membacanya:
- **Kebocoran nama berkas hilang.** Model ikut nama salah 30/40 → 2/40; konflik tertangkap 0/40 → 7/40; tautan salah pada
  nama salah 12 → 2.
- **Kondisi netral identik** (KNOWN 16/19 tindakan benar, 4/19 status benar). Inilah kemampuan visual yang sebenarnya.
- **Total tindakan benar turun (48 → 33) karena kondisi "nama benar" tidak lagi tertolong nama berkas.** Angka lama 16/19
  dan 19/21 di kondisi itu adalah salinan nama berkas, bukan pengenalan visual. Uji berpasangan KNOWN salah vs benar sekarang
  +0,105 (CI -0,105 sampai +0,316); D23 -0,632 (-0,842 sampai -0,421): nama berkas tidak lagi menentukan jawaban.
- **Kasus 2 (OTHER + nama benar tapi tidak terdaftar) turun 17/21 → 3/21.** Kode tahap 2 hanya mencocokkan nama ke
  varietas terdaftar; nama varietas tidak terdaftar belum dipakai sebagai sinyal CANDIDATE. Ini perbaikan berikutnya.
- **Foto Indonesia (ind6):** KNOWN netral 13/16 tindakan benar (D23 11/16), tautan salah 1 (D23 2); KNOWN nama asli 12/16
  (D23 12/16), dengan 3 foto yang bertentangan dengan nama berkas sekarang masuk REVIEW_MISMATCH.

Berkas: `hasil_eksperimen/foto_two_stage_2026-11-12/` (`LAPORAN_M2.md`, `skor/`, `skor_ablasi_fusi_lama/`); D23:
`hasil_eksperimen/foto_nama_berpasangan_2026-11-07/skor/hasil_skor.md`.

### 6.9 Skor gabungan workbook akhir (atribut + foto sekaligus)

Satuannya: 1 sel atribut = 1 unit, 1 link foto = 1 unit. Link foto dihitung benar hanya kalau fotonya KNOWN, kolom
varietasnya benar, **dan** masuk ke baris Gambar yang benar.

| Run | Sel atribut F1 | Link foto benar / salah / terlewat | **Gabungan P / R / F1** |
|---|---|---|---|
| S01 | 1,000 | 4 / 0 / 2 | 1,000 / 0,957 / 0,978 |
| S02 | 1,000 | 4 / 0 / 2 | 1,000 / 0,960 / 0,980 |
| S03 | 1,000 | 4 / 1 / 0 | 0,970 / 1,000 / 0,985 |
| **Indonesia S01-S03, D24** | **1,000** | **12 / 1 / 4** | **0,992 / 0,969 / 0,980** |
| Indonesia S01-S03, D23 | 1,000 | 9 / 3 / 7 | 0,976 / 0,945 / 0,960 |
| P01 + PVT, kartu terlihat* | 0,964 | 8 / 5 / 10 (D23 12 / 7 / 6) | 0,987 / 0,910 / 0,947 (D23 0,950) |
| P01 + PVT, kartu tertutup* | 0,964 | 2 / 4 / 16 (D23 3 / 5 / 15) | 0,989 / 0,895 / 0,940 (D23 0,940) |

\*Gold atribut P01 diverifikasi penulis tanpa koreksi; kunci sel dibangun dari gold itu, jadi skor tetap.

Hati-hati membacanya: sel atribut jauh lebih banyak daripada link foto (S01-S03: 112 sel vs 19 link), jadi atribut yang
sempurna mengangkat angka total. Klaim utama tetap memakai skor terpisah: 6.2 untuk atribut, 6.6-6.8 untuk foto.

### 6.10 Baris template baru (skema dinamis)

Fitur tambahan: atribut tanpa pasangan bisa otomatis dijadikan **baris baru** di bawah 60 baris template. Diuji 3 kali
(urutan R01 → N07 → N09 → R02, data dan sistem lama): 84-85 atribut tanpa pasangan menjadi **40 baris baru**, tidak ada yang
menduplikasi baris template, dan kemiripan antarpengulangan 70-78%. Status: uji kelayakan, belum metode tervalidasi. Semua
run di dokumen ini menonaktifkan fitur ini (`KMS_DYNAMIC_SCHEMA=0`).

### 6.11 Perbandingan model visi (D26, 14 Nov 2026)

Harness, input, registri, deskripsi varietas, kanonik, varietas DB (`--db-dari-meta`), mode `two_stage`, dan skrip skor sama dengan D24; yang berbeda hanya model visi (`CABAI_KMS_EVAL_VISION_MODEL`, khusus eksperimen). Model teks tetap Gemini 3.8 Flash medium. Kandidat 1 ulangan, 271 panggilan visi per model, 0 gagal setelah percobaan ulang. Claude, GPT, dan Gemini lewat 9router dari VPS; Qwen3.8 Flash dan Grok 4.7 lewat gateway OpenAI-compatible Octa Telkomsel (`CABAI_KMS_EVAL_VISION_BASE_URL`), dijalankan dari PC di Indonesia karena gateway itu hanya melayani akses dari Indonesia (salinan harness yang sama, `runner_lokal_octa/`); skor dihitung di VPS.

| Metrik | Gemini 3.8 Flash high (D24, rerata 3 ulangan) | Qwen3.8 Flash | Grok 4.7 | Claude Opus 5.5 | GPT-6 Astra | GPT-6.1 Sol |
|---|---|---|---|---|---|---|
| Presisi jawaban KNOWN (Commons, Indonesia, PVT 2 kondisi) | 0,69-0,71 | 0,67 | 0,53 | 0,67 | 1,00 | 1,00 |
| Recall KNOWN (dari 61 foto KNOWN) | **0,51-0,56** | 0,26 | 0,15 | 0,16 | 0,08 | 0,10 |
| Dijawab KNOWN padahal bukan | 5-6 | 4 | 2 | 0 | 0 | 0 |
| PVT nama salah terdaftar: REVIEW_MISMATCH (dari 40) | 7 | **17** | 2 | 1 | 0 | 0 |
| PVT berpasangan: tindakan sesuai gold (dari 120) | 32,33 | **43** | 28 | 27 | 26 | 26 |
| PVT berpasangan: AUTO_LINK salah (dari 120) | 7,67 | 8 | 0 | 0 | 0 | 0 |
| Commons: status benar (dari 35) | **32,67** | 30 | 28 | 28 | 0 | 0 |
| Indonesia S01-S03: Top-1 KNOWN | **0,750** | 0,125 | 0,312 | 0,375 | 0,312 | 0,375 |
| PVT kartu terlihat: Top-1 KNOWN | **0,579** | 0,526 | 0,158 | 0,158 | 0 | 0 |
| PVT kartu tertutup: Top-1 KNOWN | **0,175** | 0,053 | 0 | 0 | 0 | 0 |
| PVT kartu tertutup: macro-F1 kelas gold | 0,263 | **0,406** | 0,087 | 0,095 | 0 | 0 |
| Workbook gabungan Indonesia F1 | **0,980** | 0,942 | 0,947 | 0,933 | 0,938 | 0,947 |

- **Gemini 3.8 Flash tetap paling seimbang:** recall KNOWN tertinggi dengan presisi setara, dan F1 workbook akhir tertinggi.
- **Qwen3.8 Flash paling sering menangkap nama berkas yang salah** (REVIEW_MISMATCH 17/40, tindakan sesuai gold 43/120) dan
  paling sering benar menjawab OTHER (macro-F1 kartu tertutup 0,406), tetapi hampir tidak mengenali foto Indonesia (Top-1
  0,125) dan tautan salahnya setara Gemini (8/120).
- **Claude Opus 5.5, GPT-6 Astra, GPT-6.1 Sol, dan Grok 4.7 sangat konservatif:** 0 tautan salah, tetapi recall 0,08-0,16,
  sehingga hampir semua foto masuk antrean tinjauan. Keyakinan visual yang dilaporkan model ini (sering 0,70-0,86) jarang
  melewati ambang AUTO_LINK 0,85; tanpa deskripsi morfologi (Commons, Hungarian Wax) GPT tidak menjawab KNOWN atau OTHER.
- **Kondisi kartu terlihat sebagian mengukur pembacaan label:** Gemini dan Qwen membaca tulisan kartu (mis. "TURIMA 2"),
  sedangkan model lain mematuhi instruksi prompt untuk tidak menjadikan tulisan kartu satu-satunya dasar.
- **Batas utama ada di data:** pada foto PVT 125 px kartu tertutup tidak ada model yang Top-1-nya melewati 0,21.
- **Catatan keadilan:** prompt dan ambang AUTO_LINK 0,85 dikembangkan bersama Gemini; presisi/recall KNOWN adalah pembanding
  yang tidak bergantung ambang. GLM 5.2 (Octa) tidak dinilai karena tidak menerima gambar.

Berkas: `hasil_eksperimen/model_visi_2026-11-14/` (`LAPORAN_D26.md`).

---

## 7. Hal yang pernah salah dan sudah dikoreksi

| Masalah | Dampak | Perbaikan |
|---|---|---|
| **Mock diam-diam** (D18): kalau model visi gagal, kode lama memakai jawaban tiruan | 19 dari 160 foto Commons run 1 Nov bukan jawaban model | Kegagalan sekarang menjadi error; foto dijalankan ulang |
| **Kolom varietas salah** di N07 dan R02 | Nama kolom di workbook akhir salah | Pembanding header tidak peka huruf besar-kecil |
| **Data bukan level varietas** (D19) | Spesies, jenis umum, dan nama tipe ikut dinilai sebagai "varietas" | Dikeluarkan ke arsip dalam 4 tahap; gold dan daftar foto disaring |
| **Embedding lemah** (D22) | 21% butir semantik tidak masuk kandidat reranker | Ganti ke bge-m3; Hit@8 0,789 → 1,000 |
| **Skrip uji visi tertinggal dari produksi** | Setelah D20 skrip uji tidak mengirim deskripsi varietas ke model | Diperbaiki 7 Nov; semua run foto di dokumen ini memakai versi yang sudah diperbaiki |
| **Gold Commons usang** (D23) | 3 foto masih bergold REVIEW_MISMATCH setelah registri berubah | Diubah ke CANDIDATE dengan catatan alasan |
| **Nama berkas bocor ke model visi** (D24) | Model menyalin varietas dari nama berkas (30/40 nama salah diikuti); pemeriksaan silang tidak independen; skor "nama benar" terlalu tinggi | Visi dua tahap: model buta nama berkas, nama dicocokkan kode, konflik dicek di fusi; 271 foto dijalankan ulang 12 Nov |

---

## 8. Batasan yang perlu jujur disampaikan

1. **Kunci jawaban diverifikasi penulis sendiri.** Konsisten (kappa 0,97), tetapi belum dicek pakar independen.
   Gold atribut P02 (varietas lokal) belum diverifikasi dan tidak dipakai untuk skor utama.
2. **Data kecil setelah pembersihan level varietas:** 7 workbook dinilai, foto Commons tinggal 35 (7 terdaftar), foto
   Indonesia 6 foto unik.
3. **Varietas Indonesia yang mirip belum bisa dikenali dari foto** (PVT kartu tertutup Top-1 0,175 ± 0,030 dari 3 ulangan; D23
   0,211), dan tautan otomatis yang salah masih lolos (3-4 per ulangan; ulangan 1: 4 dari 6). Ambang AUTO_LINK 0,85 belum cukup aman pada foto ini.
4. **Model visi tidak deterministik.** Foto D24 dijalankan 3x per kondisi: 84,2% keputusan foto ulang dan 87,2% keputusan
   nama berkas berpasangan sama di ketiga ulangan. SB antar-ulangan kecil (PVT kartu terlihat Top-1 ± 0,053), tetapi hanya
   mengukur variasi model, bukan ketidakpastian sampel. D23 hanya satu run, jadi selisih kecil D24 vs D23 tidak diklaim.
5. **Nama varietas tidak terdaftar di nama berkas belum dipakai** sebagai sinyal CANDIDATE (kasus 2 turun 17/21 → 3/21 setelah
   D24). Konflik nama terdaftar yang salah baru tertangkap 7/40, karena sebagian besar foto PVT berakhir REVIEW_UNCERTAIN.
6. **Tidak ada penolakan otomatis untuk foto yang bukan cabai.** Foto seperti itu masuk ke review.
7. **Retrieval belum terbukti perlu** untuk template 60 baris (S3 tanpa retrieval sama baiknya di data lama).
8. **Evaluasi lewat harness**, bukan jalur produksi penuh (Drive + KMS); uji paritas belum dijalankan.

---

## 9. Kamus istilah

| Istilah | Arti sederhana |
|---|---|
| Atribut | Satu kolom/label di spreadsheet sumber, mis. "Warna Buah Matang" |
| Template kanonik | Format baku 60 baris yang dipakai KMS |
| Pemetaan (mapping) | Memasangkan atribut sumber dengan satu baris template |
| NULL | "Atribut ini tidak punya pasangan di template" |
| Retrieval / embedding | Mencari baris template yang teksnya paling mirip secara makna |
| Hit@k | Baris yang benar ada di k kandidat teratas hasil retrieval |
| MRR | Mean Reciprocal Rank: rata-rata 1/peringkat baris yang benar (1,0 = selalu peringkat pertama) |
| Reranker | LLM yang memilih satu dari kandidat hasil retrieval, atau menjawab NULL |
| Verifier | Pemeriksa otomatis berbasis aturan (bukan AI) |
| AUTO_ACCEPT / AUTO_LINK | Ditulis otomatis ke workbook |
| REVIEW_UNCERTAIN / REVIEW_MISMATCH | Tidak ditulis; menunggu manusia (ragu / nama file bertentangan dengan foto) |
| CANDIDATE | Foto varietas baru; masuk antrean, tidak ditulis |
| KNOWN / OTHER / UNCERTAIN | Varietas terdaftar / cabai lain tidak terdaftar / tidak bisa ditentukan |
| Registri | Daftar varietas yang dikenali pada satu run (dari spreadsheet run) |
| Pengembangan (dev) vs uji baru (held-out) | Data yang dilihat saat membangun sistem vs data yang disimpan khusus untuk menilai |
| Gold / kunci jawaban | Jawaban benar yang dipakai untuk menilai sistem |
| Macro-F1 | F1 dihitung per golongan, lalu dirata-rata |
| Top-1 | Jawaban pertama model langsung tepat |
| Harness | Skrip yang menjalankan pipeline produksi tanpa klik di website |
| Mock | Jawaban tiruan untuk pengujian kode, bukan jawaban model sungguhan |

---

## 10. Di mana berkasnya

| Yang dicari | Lokasi |
|---|---|
| Semua input dan output sistem | `dataset_eksperimen/` (baca `KETERANGAN_DATA.txt`) |
| Hasil atribut bge-m3 | `dataset_eksperimen/4_hasil_sistem/I_atribut_bge-m3_39f4213/` |
| Hasil foto terbaru (D24, semua set) | `dataset_eksperimen/4_hasil_sistem/L_visi_dua_tahap_D24/` |
| Hasil foto D23 (pembanding) | `dataset_eksperimen/4_hasil_sistem/J_foto_ulang_D20_bge-m3/`, `K_nama_file_berpasangan/` |
| Skor retrieval (Hit@k, MRR) | `data_evaluasi/hasil_eksperimen/hasil_retrieval/banding_embedding/ringkasan.csv` |
| Skor atribut end-to-end | `data_evaluasi/hasil_eksperimen/skor_atribut_e2e_bge-m3/skor_atribut_e2e.md` |
| Skor foto D24 + ablasi + laporan perbandingan | `data_evaluasi/hasil_eksperimen/foto_two_stage_2026-11-12/` (`LAPORAN_M2.md`) |
| Perbandingan model visi D26 | `data_evaluasi/hasil_eksperimen/model_visi_2026-11-14/` (`LAPORAN_D26.md`) |
| Skor foto dan nama file berpasangan D23 | `data_evaluasi/hasil_eksperimen/foto_ulang_2026-11-07/skor/`, `foto_nama_berpasangan_2026-11-07/skor/` |
| Keputusan desain (D19-D24) | `docs/DESIGN_DECISIONS.md` |
| Klasifikasi level varietas | `data_evaluasi/KLASIFIKASI_LEVEL_VARIETAS.md` |
| Lembar verifikasi bagian foto PVT | `data_evaluasi/gambar/manifest/lembar_gold_kanonik_foto_pvt.xlsx` |
| Paper terbaru | `docs/paper/paper_ieee_draft_v11.pdf` (angka masih versi lama, lihat Bagian 11) |

---

## 11. Riwayat: angka di draf paper v11 (4 November 2026)

Angka ini memakai data sebelum pembersihan level varietas, embedding MiniLM, dan model visi yang hanya menerima nama
varietas. Jangan dicampur dengan angka di atas.

| Bagian | Metrik | Skor paper v11 |
|---|---|---|
| Atribut (uji baru) | F1 S4 / precision / recall / recall NULL | 0,978 [0,929; 1,000] / 1,000 / 0,958 / 1,000 |
| | Pembanding S1 / S2 / S2+τ / S3 | 0,621 / 0,377 / 0,460 / 1,000 |
| | Ditulis otomatis benar / ke review | 128/129 / 164 dari 293 |
| Retrieval (104 butir semantik) | Hit@1 / Hit@8 / MRR | 0,404 / 0,779 / 0,534 |
| Isi sel (uji baru) | F1 posisi / ketat | 0,946 / 0,591 (1,000 setelah perbaikan kolom varietas) |
| Foto Commons (160) | Macro-F1 / Top-1 / tautan otomatis benar | 0,640 [0,531; 0,728] / 72/99 / 64/87 |
| | Tautan benar: informatif / netral / menyesatkan | 35/36 / 29/45 / 0/6 |
| | Bagian tanaman benar | 140/146 |
| Foto Indonesia (12 x 3) | Macro-F1 / Top-1 / tautan otomatis benar | 0,706 / 0,773 / 15/24 |
| Workbook akhir | F1 (Indonesia / Commons) | 0,820 (0,872 / 0,677) |

Rincian versi lama: `data_evaluasi/hasil_eksperimen/analisis_paper.md`, `analisis_revisi_dosen.md`,
`workbook_gabungan/hasil_skor.md`, `foto_indonesia/hasil_skor.md`, dan riwayat git berkas ini (sebelum commit perubahan ini).
