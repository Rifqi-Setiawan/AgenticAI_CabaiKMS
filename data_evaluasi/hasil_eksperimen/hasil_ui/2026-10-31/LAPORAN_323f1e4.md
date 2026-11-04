# Laporan eksekusi UI Cabai-KMS — 323f1e4
Sumber angka: Ringkasan run UI. Tidak menilai akurasi, tidak membuka gold.
UI: http://127.0.0.1:8501/
Semua run A/B termasuk N08VAR sudah dicoba; 8 run ekspor lengkap, 2 penolakan yang diizinkan. F1–F8 menunggu tautan.

- B-S01: 20:50:43–21:00:15 WIB (572 detik teramati); mapped=21, review=2, no_write=0, images=12, vision=12. Galat: tidak ada galat eksekusi tercatat. 
- B-S03: 21:01:33–21:11:00 WIB (567 detik teramati); mapped=29, review=11, no_write=0, images=12, vision=12. Galat: tidak ada galat eksekusi tercatat. 
- B-S04: 21:12:17–21:14:59 WIB (162 detik teramati); mapped=tidak tersedia, review=tidak tersedia, no_write=tidak tersedia, images=tidak tersedia, vision=tidak tersedia. Galat: Struktur workbook belum dapat diproses. Periksa sheet, orientasi, header, dan kolom varietas.. 
- A-N07: 21:20:05–21:29:02 WIB (537 detik teramati); mapped=69, review=49, no_write=0, images=0, vision=0. Galat: tidak ada galat eksekusi tercatat. 
- A-R01: 21:29:44–21:32:28 WIB (164 detik teramati); mapped=13, review=11, no_write=0, images=0, vision=0. Galat: tidak ada galat eksekusi tercatat. 
- A-N08: 21:33:05–21:33:17 WIB (12 detik teramati); mapped=tidak tersedia, review=tidak tersedia, no_write=tidak tersedia, images=tidak tersedia, vision=tidak tersedia. Galat: Struktur workbook belum dapat diproses. Periksa sheet, orientasi, header, dan kolom varietas.. 
- A-N08VAR: 21:33:27–21:38:46 WIB (319 detik teramati); mapped=22, review=14, no_write=0, images=0, vision=0. Galat: tidak ada galat eksekusi tercatat. 
- B-S02: 21:39:24–21:47:17 WIB (473 detik teramati); mapped=25, review=3, no_write=0, images=12, vision=12. Galat: tidak ada galat eksekusi tercatat. 
- A-R02: 21:48:06–21:55:00 WIB (414 detik teramati); mapped=53, review=35, no_write=0, images=0, vision=0. Galat: tidak ada galat eksekusi tercatat. 
- A-N09: 21:55:35–22:05:31 WIB (596 detik teramati); mapped=80, review=55, no_write=0, images=0, vision=0. Galat: tidak ada galat eksekusi tercatat. 

Unduhan sukses memakai tombol biasa Unduh pemetaan lengkap (CSV), Unduh hasil multimodal lengkap (CSV), Unduh hasil asli. Event downloadWillBegin dan completed disimpan per folder. Isi CSV tidak diubah; hanya nama berkas diganti.
S04 dan N08 asli ditolak: Struktur workbook belum dapat diproses. Periksa sheet, orientasi, header, dan kolom varietas. Screenshot galat_input.png, bukan screenshot ringkasan run yang tidak tersedia.
Durasi adalah waktu selesai TERAMATI dengan polling, bukan timing internal pipeline.
Antrean kandidat UI menyatakan 12 kandidat. Nama/nomor tampilan dicatat di catatan_kandidat.txt; ID DB tidak ditampilkan/tidak diverifikasi. Tidak ada penghapusan atau kurasi.
Galat MediaFileStorageError sebelumnya tidak muncul pada inspeksi tab kandidat kali ini; ini bukan pembuktian seluruh jalur media bebas galat.
RUNLOG memuat riwayat percobaan commit sebelumnya dengan commit eksplisit; folder percobaan pertama/kedua terpisah, tidak ditimpa.
Tidak ada perubahan aplikasi/config/model, deploy/restart/commit/push/merge atau klik review/Commit/stage.
Keterbatasan: belum ada F1–F8, tidak memverifikasi akurasi, tidak menghitung metrik penilaian. Screenshot tersimpan tetapi keterbacaan visual seluruh screenshot belum diverifikasi.