# Panduan untuk sesi penulisan paper (serah terima, 2 November 2026)

Bacalah ini lebih dulu bila memulai sesi baru. Eksperimen dan evaluasi **sudah selesai**; sesi berikutnya hanya menulis (paper konferensi dan/atau buku TA). Pengguna berkomunikasi dalam bahasa Indonesia santai; paper bahasa Inggris.

## 1. Peta dokumen (semua di `D:\\college\\Semester 6\\Penulisan Proposal\\project\\`)

| Kebutuhan | Berkas |
|---|---|
| Rancangan paper konferensi (struktur, halaman, tabel, risiko tinjauan) | `docs/RANCANGAN_PAPER_KONFERENSI.md` |
| Rancangan buku TA, kesenjangan metrik proposal vs hasil | `docs/RANCANGAN_PAPER_FINAL.md` |
| **Semua hasil dan angka** (bagian 1 sampai 13) | `docs/HASIL_SEMENTARA_EKSPERIMEN.md` |
| Protokol, hipotesis RQ1 sampai RQ7, baseline, deviasi D1 sampai D10 | `docs/SKENARIO_EKSPERIMEN.md`, `docs/RENCANA_EVALUASI.md` |
| Desain fitur (atribut baru, skema dinamis) | `docs/RANCANGAN_ATRIBUT_BARU.md`, `docs/RANCANGAN_KANONIK_DINAMIS.md`, `docs/DESIGN_DECISIONS.md` (D14 sampai D17) |
| Status dan sisa pekerjaan | `data_evaluasi/STATUS_PROGRES.md` |
| Data mentah semua run, checksum | `data_evaluasi/hasil_eksperimen/` (`README.md` = indeks) |
| Analisis terhitung | `hasil_eksperimen/analisis_lanjut.md`, `analisis_s3.md`, `analisis_rq4.md`, `tabel_kasus_l3.md`, `analisis_kanonik_dinamis_v3.md` |
| Skrip analisis | `data_evaluasi/skrip/` |
| Gold, asal, lembar verifikasi | `data_evaluasi/gold/final/`, `gambar/manifest/gold_gambar_manifest_final.csv`, `README_DATA_EVALUASI.md` |
| Proposal LaTeX (di VPS) | `/srv/hermes-control/personal/proposal/src/` (Bab 4 dan 5 masih template EKG) |
| Kode sistem | GitHub `Rifqi-Setiawan/AgenticAI_CabaiKMS`, branch main (terakhir `7b5a19c`); di VPS `/srv/hermes-control/services/agentic-ai-cabai-kms` |

Backup lokal: `D:\\college\\Semester 6\\Penulisan Proposal\\backup_skripsi_2026-11-02_v3.zip` (docs + data_evaluasi, memuat gold).

## 2. Angka kunci (dari HASIL_SEMENTARA)

- **Mapping F1 held-out:** S4 0,978 (0,950 sampai 1,000); S4 vs S1 +0,357, S4 vs S2 +0,602, p Holm < 0,0001. Stratum semantik: S4 0,923 vs S2 0,234. Dev 0,909.
- **Recall atribut baru:** S4 vs S2 +0,978, p Holm < 0,0001.
- **S3 (penilai melihat 60 baris, tanpa retrieval):** F1 held-out 1,000 vs S4 0,978, selisih -0,022 tidak signifikan (p Holm 0,305). Retrieval tidak terbukti lebih akurat pada katalog 60 baris. S3 hanya aproksimasi, hanya dataset atribut tunggal.
- **Foto Commons (160, UI):** V3 macro-F1 0,640 (0,531 sampai 0,728), Top-1 KNOWN 0,727; V2 (nama file) 0,314. V3 identik dengan V1. H3: V3 vs V2 pada nama file menyesatkan +0,259, p Holm 0,145 (tidak signifikan). H4 (recall OTHER V3 vs V1): 0,667 vs 0,667, tidak didukung. Angka ini sudah terkoreksi D18 (19 foto mock dijalankan ulang, 4 Nov 2026).
- **Foto Indonesia (L3):** cocok 7, 8, 6 dari 10 (S01 sampai S03, status visual mentah); S04 ditolak.
- **UI = harness** untuk atribut (RQ5 didukung).
- **F2 skema dinamis versi 3 (satu-satunya yang pembawa klaim):** 84 sampai 85 atribut tanpa padanan menjadi 40 baris; 0 duplikat dengan template; F1 template R01 0,667, N07 1,000 (+0,026), N09 1,000, R02 1,000; Jaccard antar pengulangan 0,70 sampai 0,78; 0 kegagalan. Versi 1 dan 2 dilaporkan sebagai iterasi (v2 5 dari 12 run tidak sah).
- **Uji UI produksi dengan flag aktif:** 8 baris akuisisi, Excel 68 baris data; antrean review konsisten setelah D10; 8 baris disetujui kurator.

## 3. Aturan yang harus dijaga

1. **Gold diverifikasi langsung oleh penulis** (`terverifikasi_v1`). Tidak ada anotator kedua dan tidak ada kappa antar-anotator.
2. **Hanya F2 versi 3** untuk klaim; hipotesis yang tidak didukung dilaporkan apa adanya (H3 sebagian, H4, S3).
3. **Jangan membuat klaim** performa pada cabai Indonesia dari foto Commons (proksi luar negeri).
4. **Paten:** Cabai-KMS diajukan ke DJKI April 2026; bagian baru (skema dinamis) dikonsultasikan dahulu ke pembimbing sebelum dipublikasikan. Cek lisensi data (`gambar/manifest/ATRIBUSI_LISENSI.csv`) sebelum merilis.
5. **Rahasia:** jangan menampilkan atau mengirim token, key 9Router, password database. Token kurator pernah tertulis di chat (perlu diganti); `ui.env` memuat `DATABASE_URL` berpassword.
6. **Gold tidak boleh ada di VPS** dan tidak boleh terlihat oleh Jarvis (agen yang menjalankan UI).
7. Akses VPS: `ssh myvps`, lalu `sudo -i`; jangan mencoba kunci SSH lain. Layanan: `sudo -u hermes XDG_RUNTIME_DIR=/run/user/999 systemctl --user restart cabai-kms-api.service cabai-kms.service`.
8. Untuk menjalankan eksperimen atau UI lewat web, minta pengguna menyuruh Jarvis (beri instruksi sederhana). Jarvis dilarang menekan Commit, Terapkan Koreksi, Approve, Merge, Discard, dan membuka gold.

## 4. Status sistem produksi

Flag `KMS_DYNAMIC_SCHEMA=1` aktif di `runtime.env` (API) dan `ui.env` (UI). Harus ada di kedua berkas karena pipeline berjalan di proses UI. Kurasi baris akuisisi memerlukan token berperan curator (kolom "Masuk sebagai kurator" di panel KMS; token dicetak oleh `sudo /root/tampilkan_token_kurator.sh` di terminal VPS).

## 5. Pekerjaan yang tersisa untuk penulisan

1. Venue (nama, format, batas halaman, tenggat, double-blind) belum diketahui; tentukan dahulu.
2. Metrik proposal yang belum dihitung dan bisa dihitung dari data yang ada: F1 kelas NULL, macro-F1 antar domain, Selective Risk@Coverage, ECE, latency (RUNLOG), human review rate. Hit-Rate@k dan MRR perlu dump retrieval di VPS (tanpa gold). Detail: `RANCANGAN_PAPER_FINAL.md` bagian 4.
3. Opsional memperkuat paper: S3 vs S4 pada katalog 101 baris; dua urutan dataset F2 tambahan.
4. Tulis draf (urutan: Metode dan Hasil dahulu), buat gambar, lalu abstrak.
5. Tugas non-penulisan yang masih ada pada pengguna: ganti token kurator, hapus key 9Router lama, ganti password database `cabai_app` (opsional), salin backup ke penyimpanan lain.
