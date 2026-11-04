# Arsip hasil eksperimen

Salinan lokal semua keluaran eksperimen, ditarik dari VPS oleh `skrip/arsipkan_hasil.sh` ke `hasil_eksperimen/`.
Tidak ada berkas yang diubah setelah ditarik; `SHA256SUMS_lokal.txt` mencatat hash tiap berkas.

| Folder | Isi | Pembuat |
|---|---|---|
| `hasil_ui/<tanggal>/atribut`, `atribut_n08var`, `kombinasi`, `gambar` | Per run UI: `mapping.csv`, `vision.csv`, `hasil_asli.xlsx`, `ringkasan.png`, `download_events.txt`; `RUNLOG.csv`, laporan, catatan kandidat | Jarvis (UI) |
| `hasil_ui/<tanggal>/kombinasi_323f1e4_pra_D6` | Run foto sebelum perbaikan D6 (disimpan, tidak dipakai sebagai hasil) | Jarvis |
| `hasil_harness/<tanggal>/rep<n>/<jenis>/<ID>` | Per run harness: `mapping.csv`, `vision.csv`, `hasil_asli.xlsx`, `canonical.csv`, `trace.json`, `meta.json`; `RUNLOG_harness.csv`, `SHA256SUMS.txt`, log | harness_vps.py |
| `hasil_harness/2026-11-01_bc3c21b/rep0_format_lama` | Run harness pertama tanpa `trace.json`/`hasil_asli.xlsx` (data inti sama, commit sama) | harness |
| `hasil_dinamis/urutan_B`, `urutan_C` | F2 versi 2 (5 dari 12 run tidak sah karena penilai kehabisan waktu) dan versi 3 (dipakai untuk klaim; 0 kegagalan) | harness_vps.py, run_f2b.sh, run_f2c.sh |
| `hasil_harness/2026-11-01_regresi_D9d`, `_D9e`, `2026-11-02_regresi_D10` | Regresi saklar mati setelah D9d, D9e, D10 (R01) | harness_vps.py |
| `hasil_harness/2026-11-02_S3` | Baseline S3 (aproksimasi, `--s3`): penilai melihat seluruh 60 baris; atribut R01, R02, N07, N08, N09, 3 pengulangan, 18 run (2 penolakan sah N08 asli) | harness_vps.py |
| `hasil_ui/2026-11-02` | Uji UI produksi dengan skema dinamis, tiga run (lihat `LAPORAN_UJI_UI_SKEMA_DINAMIS.md`) | Jarvis (UI) |
| `analisis_lanjut.md`, `analisis_s3.md`, `analisis_rq4.md`, `tabel_kasus_l3.md`, `analisis_kanonik_dinamis*.md` (v1 sampai v3) | Keluaran analisis dari `skrip/` (statistik, S3, RQ4, tabel L3, F2) | skrip analisis |

Setiap run punya commit dan fingerprint konfigurasi (`meta.json` atau RUNLOG). Lihat bagian 12 `docs/SKENARIO_EKSPERIMEN.md` untuk deviasi.
