# Rancangan paper konferensi (2 November 2026)

Asumsi sampai ada detail venue: bahasa Inggris, format dua kolom (IEEE atau Springer LNCS), 6 sampai 8 halaman, tinjauan oleh penelaah (peer review), submission lewat sistem konferensi. Buku TA (`RANCANGAN_PAPER_FINAL.md`) tetap dokumen terpisah dan lebih lengkap; paper ini adalah turunannya.

## 1. Pesan utama (satu kalimat)

Sebuah pipeline Agentic AI memetakan spreadsheet varietas cabai yang heterogen ke skema kanonik tetap (60 baris) secara zero-shot, menolak atribut tanpa padanan, lalu menambah baris kanonik baru tanpa duplikat; seluruhnya dievaluasi dengan protokol beku, pembanding bertingkat, dan statistik berpasangan.

## 2. Kontribusi yang diklaim (urut kekuatan bukti)

1. **Schema matching zero-shot semantik dengan penolakan (NULL):** S4 vs S1 (exact-name) +0,357 dan vs S2 (retrieval top-1) +0,602 pada held-out, CI 95% tidak memuat 0, p Holm < 0,0001. Bukti terkuat; bertumpu pada stratum semantik (S4 0,923 vs S2 0,234).
2. **Akuisisi skema kanonik dinamis tanpa duplikat:** 84 atribut tanpa padanan menjadi 40 baris (53% disatukan atau dipakai ulang), 0 duplikat dengan template, F1 template tidak turun, stabil antar pengulangan (F2 versi 3, satu urutan dataset). Ini yang paling baru (novelty), dengan batas bukti yang jelas.
3. **Protokol evaluasi yang jujur:** split dev/held-out, bootstrap berpasangan + Holm, hasil negatif dilaporkan (fusi foto H3 sebagian, recall OTHER H4, retrieval vs penilai penuh S3).

Foto dijadikan klaim pendukung, bukan utama (proksi luar negeri).

## 3. Judul kerja dan anggaran halaman (6 halaman, +2 bila diizinkan)

Judul: *Adaptive Knowledge Acquisition with Agentic LLMs: Zero-Shot Schema Matching and Dynamic Canonical Rows for a Chili Variety KMS* (alternatif: tanpa "Dynamic Canonical Rows" bila tinjauan menekankan matching).

| Bagian | Halaman | Isi |
|---|---|---|
| Abstrak | 0,2 | Masalah, metode, 3 angka kunci, batas klaim |
| 1 Pendahuluan | 0,8 | Heterogenitas spreadsheet lapangan; format baku menghalangi pakar; 3 kontribusi |
| 2 Penelitian terkait | 0,6 | LLM untuk schema matching; Agentic AI; KMS pertanian/biodiversitas |
| 3 Metode | 1,6 | Arsitektur (diagram), skema kanonik 60 baris, retrieval + rerank + verifier + NULL, akuisisi dinamis (penilai, penyatuan makna, kurasi), fusi foto singkat |
| 4 Desain eksperimen | 0,8 | Data, gold dan asalnya, split, S1 sampai S4, metrik, statistik |
| 5 Hasil dan diskusi | 1,6 | Tabel utama, stratifikasi, F2, foto ringkas, hasil negatif |
| 6 Keterbatasan dan etika | 0,3 | Gold satu verifikator, proksi, satu urutan F2 |
| 7 Kesimpulan | 0,2 | |
| Pustaka | 0,5 | Sekitar 20 sampai 25 acuan |

## 4. Tabel dan gambar (maksimal 3 gambar, 3 tabel)

- **Gambar 1:** arsitektur pipeline (multi-agen, orkestrator, skema kanonik, kurasi).
- **Gambar 2:** Mapping F1 S1/S2/S3/S4 dengan CI (dev vs held-out), stratum lookup vs semantik.
- **Gambar 3:** contoh akuisisi dinamis: atribut sumber, baris yang terbentuk, penyatuan makna, penggunaan ulang pada dataset berikutnya (alur R01, N07, N09, R02).
- **Tabel 1:** data (dataset, atribut, split).
- **Tabel 2:** hasil utama (P, R, F1, recall atribut baru, S1 sampai S4).
- **Tabel 3:** F2 versi 3 per dataset (kandidat, baris baru, digabung, dipakai ulang, F1 template).
Foto, tabel kasus L3, dan versi F2 sebelumnya masuk satu paragraf ringkas atau materi tambahan (supplementary).

## 5. Yang dipotong dari buku TA

Retrieval Hit-Rate dan MRR terperinci, ECE, latency terperinci, Tabular Update Agent, evolusi F2 v1 sampai v3 (cukup satu kalimat bahwa tiga iterasi dilaporkan di repositori), rincian UI, deviasi D1 sampai D10.

## 6. Risiko tinjauan dan cara menjawabnya

| Kritik yang mungkin | Jawaban |
|---|---|
| Gold diverifikasi satu orang | Sajikan sebagai benchmark awal; laporkan kappa anotasi ulang buta; rilis gold; CI bootstrap |
| Domain sempit (satu komoditas, 9 workbook) | Nyatakan; skema kanonik menjadi parameter, kode bersifat umum; saran multi-domain |
| S3 menunjukkan retrieval tidak terbukti | Laporkan; framing: pada katalog 60 baris penilai penuh cukup, retrieval relevan saat katalog tumbuh (skema dinamis, 101 baris); **ideal: tambah percobaan S3 vs S4 pada katalog 101 baris** (opsional, butuh satu eksperimen) |
| F2 hanya satu urutan, penilai model | Batasi klaim ke "feasibility"; tambah 2 urutan dataset berbeda bila waktu cukup (opsional) |
| Tiga iterasi setelah melihat hasil | Ungkapkan; hanya versi 3 dipakai untuk klaim |
| Kebaruan terbatas | Tekankan kombinasi penolakan NULL + akuisisi dinamis tanpa duplikat + protokol beku, bukan matching semata |

## 7. Hal yang harus dicek sebelum menulis

- **Paten:** Cabai-KMS diajukan ke DJKI April 2026. Publikasi setelah tanggal pengajuan umumnya tidak menghilangkan prioritas, tetapi bagian baru yang tidak tercakup pengajuan (mis. skema dinamis) perlu dikonsultasikan dengan pembimbing dan pihak paten sebelum diumumkan. Ini bukan nasihat hukum.
- **Lisensi data:** foto Commons punya atribusi (`gambar/manifest/ATRIBUSI_LISENSI.csv`); workbook N07 dan sumber lain harus dicek hak sebarnya sebelum data dirilis.
- **Kepenulisan:** nama pembimbing dan kontribusi.
- **Venue:** format, batas halaman, apakah double-blind (nama harus dihapus, termasuk dari repositori), tenggat, dan bahasa.

## 8. Urutan kerja

1. Tetapkan venue dan tenggatnya (menentukan format dan batas halaman).
2. Putuskan opsi tambahan: (a) S3 vs S4 pada katalog 101 baris, (b) dua urutan F2 tambahan. Keduanya memperkuat paper, masing-masing sekitar setengah hari di VPS.
3. Gue tulis draf LaTeX bagian demi bagian dalam bahasa Inggris, dimulai dari Metode dan Hasil (bukti sudah ada), lalu Pendahuluan, Terkait, Abstrak.
4. Gue buat gambar dari data (grafik hasil, diagram akuisisi) dan tabel.
5. Lo tinjau, cek paten dan lisensi, lalu kirim.
