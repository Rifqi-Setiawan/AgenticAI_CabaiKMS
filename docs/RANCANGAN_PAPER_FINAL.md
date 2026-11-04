# Rancangan dokumen final Tugas Akhir (2 November 2026)

Dibuat dari pembacaan proposal (`/srv/hermes-control/personal/proposal/src/`: Pendahuluan, Metodologi, Abstrak, struktur Kajian Pustaka) dan seluruh hasil eksperimen (`HASIL_SEMENTARA_EKSPERIMEN.md` bagian 1 sampai 13).
Asumsi: "paper final" = buku Tugas Akhir yang melanjutkan proposal (LaTeX, Bab 1 sampai 5). Bagian 8 memuat opsi artikel jurnal ringkas bila dibutuhkan.

## 1. Kondisi proposal sekarang

| Bagian | Kondisi | Tindakan |
|---|---|---|
| Bab 1 Pendahuluan | Lengkap: 3 rumusan masalah, 2 pernyataan masalah, 3 tujuan, 7 batasan, 2 hipotesis | Sinkronkan batasan dan tambahkan kontribusi skema dinamis (butuh persetujuan pembimbing) |
| Bab 2 Kajian Pustaka | Penelitian terkait + landasan teori (KMS, LLM, Agentic AI, standardisasi tabular, preprocessing multimodal) | Tambah: evaluasi statistik (bootstrap berpasangan, Holm), skema dinamis/penyatuan makna |
| Bab 3 Metodologi | 69 KB: arsitektur multi-agen, skema kanonik, normalisasi, implementasi, rancangan metrik | **Sinkronkan dengan implementasi final** (belum gue baca penuh; lihat bagian 4) dan tambah desain eksperimen |
| Bab 4 Hasil | **Template EKG/PVC, belum ditulis** | Tulis seluruhnya |
| Bab 5 Kesimpulan | **Template, belum ditulis** | Tulis seluruhnya |
| Abstrak ID/EN | Masih bersifat rencana ("diharapkan menghasilkan") | Tulis ulang dengan hasil |

## 2. Pemetaan proposal ke hasil eksperimen

Hipotesis proposal hanya dua. Eksperimen memakai tujuh (RQ1 sampai RQ7) yang lebih rinci; tabel ini menjembatani keduanya.

| Elemen proposal | Padanan eksperimen | Status |
|---|---|---|
| Rumusan 1 + Hipotesis 1 (schema matching zero-shot LLM lebih fleksibel daripada rule-based) | RQ1 (S4 vs S1 exact-name sebagai pembanding rule-based) dan RQ2 (recall atribut baru) | Didukung (S4 vs S1 +0,357; vs S2 +0,602; p Holm < 0,0001) |
| Rumusan 2 + Hipotesis 2 (pengaitan teks dengan citra, minim broken link) | RQ3, RQ4 (foto), RQ5 (UI = harness), tabel kasus L3 | **Sebagian**: klasifikasi foto jalan (macro-F1 V3 0,640, terkoreksi D18) tetapi H3 dan H4 tidak didukung; "broken link" belum diukur langsung (lihat bagian 4) |
| Rumusan 3 (arsitektur Agentic AI adaptif) | RQ5, RQ6, RQ7 + uji UI produksi | Didukung: UI = harness; skema dinamis tidak merusak pemetaan template (RQ6) dan menyatukan makna (RQ7) |
| Tidak ada di proposal | Skema kanonik dinamis dan kurasi (RQ6, RQ7) | **Kontribusi tambahan**; cocok dengan kata "adaptive" di judul |

## 3. Rancangan Bab 4 (Hasil dan Pembahasan)

Urutan mengikuti rumusan masalah proposal, bukan urutan kerja eksperimen.

1. **Setup eksperimen** (ringkas; detail di Bab 3): data (9 workbook, 326 atribut, 160 foto Commons + 12 foto peneliti), pembagian dev/held-out (R01, S01 sampai S04 vs R02, N07, N08, N09), varian S1/S2/S3/S4 dan V1/V2/V3, statistik, gold dan asalnya.
2. **Schema matching** (rumusan 1): tabel S4/S1/S2/S3 dengan CI (Tabel 4.x), uji berpasangan, stratifikasi lookup vs semantik (klaim bertumpu pada stratum semantik: S4 0,923 vs S2 0,234), recall atribut baru, dev vs held-out. Pembahasan: temuan S3 (retrieval tidak terbukti lebih akurat daripada penilai yang melihat 60 baris; keuntungannya mungkin pada katalog besar atau biaya).
3. **Klasifikasi foto dan pengaitan** (rumusan 2): matriks V3 3 kelas, macro-F1 dan Top-1 (CI), per kondisi nama file, fusi dan AUTO_LINK (ketepatan 0,71), H3 (tidak didukung penuh) dan H4 (tidak didukung), tabel kasus L3 (foto Indonesia).
4. **Sistem terdeploy** (rumusan 3): kesetaraan UI dan harness (RQ5), uji UI produksi dengan skema dinamis (run `8569f1d04b10`), kasus penolakan sah (S04, N08 asli).
5. **Akuisisi skema dinamis** (kontribusi tambahan): F2 versi 3 (40 baris dari 84 kandidat, 0 duplikat template, F1 template tidak turun, stabilitas Jaccard 0,70 sampai 0,78), kurasi, evolusi v1 sampai v3 sebagai evaluasi iteratif (jujur: tiga putaran perbaikan setelah melihat hasil).
6. **Pembahasan umum**: apa yang didukung, apa yang tidak, kenapa; ancaman validitas.
7. **Keterbatasan** (bagian 6 dokumen ini).
8. **Ringkasan bab**.

Bab 5: kesimpulan per tujuan (3 tujuan proposal), tiap kesimpulan menunjuk tabel bukti, plus saran (gold dua anotator, foto Indonesia berlabel, domain lain, katalog besar untuk S3, evaluasi multi-urutan F2).

## 4. Kesenjangan antara metrik proposal dan hasil yang ada

Proposal (Bab 3, bagian Metodologi dan Metrik Evaluasi) menjanjikan metrik yang belum semuanya dihitung. Pembimbing atau penguji akan membandingkan. Pilihan: hitung, atau ubah Bab 3 agar sesuai yang benar-benar diukur.

| Metrik di proposal | Sudah ada? | Tindakan |
|---|---|---|
| Hit-Rate@k, MRR (retrieval) | **Belum**: harness hanya merekam top-1 | Bisa dihitung: dump peringkat retrieval di VPS (tanpa gold, hanya embedding) lalu cocokkan dengan gold di laptop |
| Top-1 Accuracy reranking | Setara dengan recall pada butir bertarget | Sajikan sebagai Top-1 pada butir bertarget |
| Macro-F1 antar domain | Belum | Bisa dihitung dari data yang ada (domain tiap baris kanonik diketahui) |
| Precision/Recall/F1 kelas mapping dan NULL | Mapping F1 ada; **kelas NULL belum dilaporkan terpisah** | Bisa dihitung dari data yang ada |
| Top-1 / Top-3 varietas foto | Top-1 ada; **Top-3 tidak** (sistem hanya mengeluarkan satu pilihan, bukan peringkat) | Hapus Top-3 dari Bab 3 dan jelaskan alasannya |
| Routing 3-status: confusion matrix, Routing Accuracy, Selective Risk@Coverage | Matriks dan macro-F1 ada; Selective Risk belum | Bisa dihitung dari data yang ada |
| Klasifikasi bagian tanaman (DAUN, BATANG, BUAH, BUNGA) | **Tidak ada gold bagian untuk 160 foto Commons** (hanya L3 yang punya kolom bagian) | Laporkan hanya pada L3 (n kecil), atau tandai sebagai keterbatasan |
| Kalibrasi confidence (ECE) | Belum | Bisa dihitung: confidence ada di `vision.csv`, kebenaran dari gold |
| Cell-level P/R/F1 dan Update Correctness (Tabular Update Agent) | Belum | Perlu definisi gold sel; kemungkinan dihitung dari L3 saja, atau laporkan sebagai uji fungsional |
| End-to-End Pipeline Accuracy | Belum didefinisikan sebagai satu angka | Definisikan dari Mapping F1 + foto, atau ganti dengan tabel per tahap |
| Latency (rata-rata, P50, P95) | Durasi per run ada di RUNLOG | Bisa dihitung langsung |
| Token Cost | **Belum diketahui apakah tercatat** | Perlu dicek (`provider_trace`); bila tidak ada, jadikan keterbatasan |
| Human Review Rate | Belum | Bisa dihitung (REVIEW, NULL, OTHER, UNCERTAIN) |
| "Broken link" (Hipotesis 2) | **Tidak diukur langsung** | Tentukan definisi operasional (mis. tautan foto ke varietas yang salah dan tertulis) dan hitung dari L3 dan AUTO_LINK |
| Closed-Loop Self-Correction (disebut di abstrak) | Belum jelas padanannya di implementasi (ada verifier) | Pastikan istilahnya sesuai kode sebelum ditulis |

## 5. Bahasa klaim (agar tidak berlebihan)

- Tulis "terhadap gold berbantuan AI yang disetujui satu peneliti", bukan "terhadap kebenaran dasar".
- S4 lebih baik dari S1 dan S2: boleh diklaim, bertumpu pada stratum semantik (butir yang bisa diselesaikan lookup tidak membedakan varian).
- Fusi foto (H3) dan recall OTHER (H4): tulis apa adanya sebagai tidak didukung; manfaat fusi dibaca sebagai pencegahan tautan otomatis yang salah (eksploratori: pada nama file menyesatkan, 11 tautan otomatis dengan 0 benar, 21 dialihkan ke review dengan 12 benar).
- Skema dinamis: klaim hanya pada satu urutan dataset, penilai model, baris dikurasi satu peneliti. Hanya versi 3 pembawa klaim; v1 dan v2 dilaporkan sebagai iterasi.
- Foto Commons adalah proksi luar negeri; jangan klaim performa pada cabai Indonesia dari angka itu.

## 6. Keterbatasan yang wajib ada

Gold berbantuan AI tanpa kappa; foto proksi luar negeri; S3 aproksimasi dan hanya dataset atribut; F2 satu urutan; penilai akuisisi berbasis model dan nondeterministik pada tingkat butir; penulisan dokumen KMS hanya tata letak Resume Data; tiga putaran perbaikan setelah melihat hasil (D9d, D9e, D10); batasan satu sheet dan satu lokasi dari proposal.

## 7. Urutan kerja yang disarankan

1. **Keputusan lo** (bagian 9) agar ruang lingkup jelas.
2. **Hitung metrik proposal yang bisa dihitung** (bagian 4, kolom "Bisa dihitung"): gue kerjakan, tanpa eksperimen baru kecuali dump retrieval.
3. **Sinkronkan Bab 3** dengan sistem final (gue baca Bab 3 penuh dan ajukan daftar perubahan).
4. **Tulis Bab 4** dari tabel dan CI yang sudah ada, lalu **Bab 5**, lalu **Abstrak** (gue bisa buat draf LaTeX per bab).
5. Perbarui Bab 1 (kontribusi) setelah disetujui pembimbing.
6. Kompilasi dan periksa sitasi.

## 8. Opsi artikel jurnal ringkas (turunan, 6 sampai 8 halaman)

Judul kerja: *Adaptive Knowledge Acquisition with Agentic LLMs for Standardizing Heterogeneous Spreadsheets and Field Images into a Chili Variety KMS*. Struktur IMRaD: pendahuluan dan masalah; metode (arsitektur singkat, skema kanonik, akuisisi dinamis); eksperimen (gold, baseline, statistik); hasil (S4 vs S1/S2/S3, foto, F2); diskusi dan keterbatasan. Poin utama: schema matching semantik pada 60 baris (+0,357 dan +0,602), temuan jujur S3 dan fusi foto, akuisisi skema dinamis tanpa duplikat. Hanya dibuat bila lo mau mengirim ke jurnal atau seminar.

## 9. Keputusan yang dibutuhkan dari peneliti

1. "Paper final" = buku TA (rekomendasi) atau artikel jurnal, atau keduanya?
2. Skema dinamis dimasukkan sebagai kontribusi utama (mengubah Bab 1) atau sebagai bagian "pengembangan lanjutan" di Bab 4 tanpa mengubah rumusan masalah?
3. Metrik proposal yang tidak dapat dihitung (Top-3 varietas, bagian tanaman pada 160 foto, mungkin token cost): dihapus dari Bab 3 dan dijelaskan, atau dikejar dengan pekerjaan tambahan?
4. Apakah pembimbing sudah menyetujui perubahan ruang lingkup bila Bab 1 diubah?
