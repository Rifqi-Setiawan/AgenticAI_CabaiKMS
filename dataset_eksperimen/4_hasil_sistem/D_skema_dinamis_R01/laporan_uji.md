# Uji UI produksi dengan skema dinamis (2 November 2026, dijalankan Jarvis, file R01 `data_input.xlsx`)

Tiga run lewat UI produksi (sheet Resume Data, row-oriented, header Otomatis, tanpa Drive). Berkas mentah per run ada di folder ini (`run2/`, `run3/`, dan berkas di tingkat atas untuk run 1).
Pemetaan folder ke run berdasarkan urutan dan waktu berkas; angka diambil dari laporan Jarvis.

| Run | Kondisi | Run ID | Hasil |
|---|---|---|---|
| 1 | Saklar `KMS_DYNAMIC_SCHEMA` baru di env API, belum di env UI | `41f8e43bfee5` | Panel: "Akuisisi sedang NONAKTIF"; 13 atribut: AUTO_ACCEPT 2, REVIEW 11; Excel 60 baris data. Menemukan bahwa saklar harus ada di `ui.env` |
| 2 | Saklar aktif di API dan UI | `a8f2d4f6b43e` | Akuisisi AKTIF; AUTO_ACCEPT 10, REVIEW 3; Excel 68 baris data (60 + 8); 8 baris provisional; **UNRESOLVED REVIEWS 11 padahal REVIEW 3** (cacat antrean) |
| 3 | Setelah perbaikan D10 (commit `8d89e06`) | `8569f1d04b10` | UNRESOLVED REVIEWS 3 = REVIEW 3 (koordinat S, E, ketinggian lahan); Excel 68 baris data; 8 baris dipakai ulang; exact-name 1, retrieve-rerank 12; 118 detik |

Delapan baris akuisisi: kandungan klorofil daun, kandungan nitrogen daun, kelembapan permukaan daun, suhu permukaan daun, kelembapan tanah, pH tanah, suhu udara, kelembapan udara.
Seluruhnya kemudian disetujui peneliti (status approved) lewat API dengan token kurator. Jarvis tidak menekan Commit, Terapkan Koreksi, Approve, Merge, atau Discard dan tidak membuka gold.
