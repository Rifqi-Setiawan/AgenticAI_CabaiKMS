# Laporan M2: visi dua tahap (buta nama berkas), 12 Nov 2026

## Ringkasan

- **Perubahan.** Model visi tidak lagi menerima nama berkas maupun caption. Nama berkas dicocokkan ke registri oleh kode biasa (tahap 2), lalu kedua sinyal digabung di `fuse_photo_signals`. Mode lama tetap tersedia sebagai baseline lewat `CABAI_KMS_VISION_MODE=single_call`.
- **Kebocoran nama berkas hilang.**
  - Pada foto PVT dengan nama varietas terdaftar yang salah, model kini mengikuti nama berkas pada 2/40 foto (sebelumnya 30/40).
  - Penautan otomatis yang salah turun dari 17/120 menjadi 8/120.
  - REVIEW_MISMATCH yang dulu tidak pernah muncul (0/40) sekarang muncul 7/40.
- **Angka yang tampak turun (tindakan sesuai gold PVT, dari 48/120 menjadi 33/120) berasal dari skor lama yang terlalu tinggi, bukan dari kemunduran.**
  - Pada nama netral, yang tidak pernah bocor, hasil lama dan baru identik: status benar 4/19 foto KNOWN, tindakan sesuai gold 16/19.
  - Selisihnya berasal dari kondisi BENAR. Di sana sistem lama menjawab benar karena menyalin nama berkas, bukan karena mengenali tanaman.
  - Kemampuan visual yang sebenarnya pada foto PVT kartu tertutup memang rendah.
- **Workbook gabungan Indonesia naik** dari F1 0.960 menjadi 0.980. Tautan foto yang salah turun dari 3 menjadi 1, dan yang terlewat dari 7 menjadi 4.
- **Commons turun dari 35/35 menjadi 32/35.** Tiga foto berubah. Satu foto Hungarian Wax yang dulu tertaut karena namanya sekarang ditandai REVIEW_MISMATCH, dan satu foto cayenne salah tertaut ke Hungarian Wax.

## Desain perbandingan

| | Run lama (7 Nov) | Run baru (12 Nov) |
|---|---|---|
| Mode visi | single_call (nama berkas di prompt) | two_stage (model buta nama berkas) |
| Aturan fusi | lama | baru (`independent_signals=True`) |
| Input foto, registri, deskripsi varietas, kanonik P01/S01-S03 | sama | sama |
| Varietas DB | `[]` | dikunci ke meta run lama (`--db-dari-meta`), jadi tetap `[]` |
| Model | `ag/gemini-3.8-flash-high` via 9Router | sama |
| Jumlah panggilan visi | 271 | 271, 0 gagal |

- **Validasi skrip skor.** Kedua skrip skor menghasilkan laporan lama yang byte-identik bila dijalankan ulang pada data lama.
- **Ablasi.** Jawaban visual run baru digabung ulang dengan aturan fusi lama (`ablasi_fusi_m2.py --fusi lama`) tanpa memanggil model lagi. Ini memisahkan efek model yang buta nama berkas dari efek aturan fusi baru.
- **Uji kewarasan.** `--fusi baru` memberi tindakan yang 271/271 sama dengan yang tercatat saat run.

## 1. Desain nama file berpasangan (D23), set utama

PVT berisi 40 foto kartu tertutup (19 KNOWN, 21 OTHER). Setiap foto dijalankan dengan tiga varian nama berkas.

### Kebocoran: varian SALAH_TERDAFTAR (nama varietas terdaftar yang salah)

| Metrik (40 foto) | Lama | Baru, fusi lama (ablasi) | **Baru** |
|---|---|---|---|
| Model menyebut varietas dari nama berkas | 30/40 | 2/40 | **2/40** |
| REVIEW_MISMATCH (jawaban yang diharapkan) | 0/40 | 3/40 | **7/40** |
| AUTO_LINK ke varietas salah | 12/40 | 3/40 | **2/40** |
| Tindakan sesuai gold | 0/40 | 3/40 | **7/40** |

### Per sel

| Gold | Nama berkas | Status visual benar, lama → baru | Tindakan sesuai gold, lama → baru | AUTO_LINK salah, lama → baru |
|---|---|---|---|---|
| KNOWN | NETRAL | 4/19 → 4/19 | 16/19 → 16/19 | 3 → 3 |
| KNOWN | BENAR | 16/19 → 3/19 | 12/19 → 4/19 | 0 → 0 |
| KNOWN | SALAH_TERDAFTAR | 1/19 → 3/19 | 0/19 → 6/19 | 7 → 2 |
| OTHER | NETRAL | 0/21 → 0/21 | 3/21 → 3/21 | 2 → 1 |
| OTHER | BENAR | 19/21 → 0/21 | 17/21 → 3/21 | 0 → 2 |
| OTHER | SALAH_TERDAFTAR | 0/21 → 0/21 | 0/21 → 1/21 | 5 → 0 |
| **Total PVT** | | | **48/120 → 33/120** | **17/120 → 8/120** |

### Ablasi: dari mana tiap perubahan berasal

| Total PVT (120) | Lama | Hanya model buta nama | + aturan fusi baru |
|---|---|---|---|
| Tindakan sesuai gold | 48 | 29 | **33** |
| AUTO_LINK salah | 17 | 12 | **8** |

- **Model yang buta nama berkas** menghapus jawaban yang hanya menyalin nama berkas. Akibatnya skor BENAR yang terlalu tinggi ikut turun (48 → 29), dan AUTO_LINK salah turun dari 17 menjadi 12.
- **Aturan fusi baru** menambah 4 tindakan benar dan mengurangi 4 AUTO_LINK salah. Sumbernya dua hal:
  - kontradiksi tetap ditangkap walaupun keyakinan model rendah;
  - "Rikub 1" dan "Rikub 2" kini dibedakan.
- Aturan fusi hanya mengubah 8 dari 271 tindakan, dan seluruhnya pada set PVT berpasangan.

**Uji berpasangan setelah perubahan.** Untuk foto KNOWN, perbandingan SALAH_TERDAFTAR vs BENAR kini +0.105 (CI −0.105 sampai +0.316), padahal sebelumnya −0.632 (CI −0.842 sampai −0.421). Artinya nama berkas tidak lagi menentukan jawaban.

### Indonesia, 6 foto × S01-S03

| Sel | Tindakan sesuai gold, lama → baru | AUTO_LINK salah, lama → baru |
|---|---|---|
| KNOWN NETRAL (16) | 11 → 13 | 2 → 1 |
| KNOWN BENAR (16) | 12 → 12 (3 jadi REVIEW_MISMATCH) | 0 → 0 |
| OTHER NETRAL (2) | 1 → 1 | 0 → 1 |
| OTHER BENAR (2) | 2 → 1 | 0 → 1 |

## 2. Run ulang foto dan workbook gabungan

| Set | Metrik | Lama | Baru |
|---|---|---|---|
| commons35 | Status benar | 35/35 | 32/35 |
| | Top-1 KNOWN | 1.000 | 0.714 (5/7) |
| | AUTO_LINK benar | 7/7 | 5/6 |
| | Tindakan sesuai gold | 35/35 | 32/35 |
| Indonesia S01-S03 | Status benar | 15/18 | 13/18 |
| | Macro-F1 kelas gold | 0.734 | 0.633 |
| | Top-1 KNOWN | 0.812 | 0.750 |
| | AUTO_LINK benar | 12/12 | 12/13 |
| | Bagian tanaman benar | 15/18 | **18/18** |
| | **Workbook gabungan F1** | 0.960 | **0.980** |
| | Tautan foto benar / salah / terlewat | 9 / 3 / 7 | **12 / 1 / 4** |
| pvt40 kartu terlihat | Status benar | 27/40 | 25/40 |
| | Top-1 KNOWN | 0.632 | 0.579 |
| | Tindakan sesuai gold | 30/40 | 25/40 |
| | Workbook F1 | 0.950 | 0.947 |
| pvt40 kartu tertutup | Status benar | 4/40 | 3/40 |
| | Top-1 KNOWN | 0.211 | 0.158 |
| | Tindakan sesuai gold | 11/40 | 9/40 |
| | Workbook F1 | 0.940 | 0.940 |

Pada set ini aturan fusi lama dan baru memberi hasil yang identik, jadi semua perubahan berasal dari model yang kini buta nama berkas, ditambah variasi model.

### Contoh foto yang berubah

| Foto | Lama | Baru | Arti |
|---|---|---|---|
| `cabai katokon - posisi bunga ...` (S01-S03) | OTHER → CANDIDATE | KNOWN Katokkon → AUTO_LINK | Nama yang salah eja ("katokon") dulu menyesatkan model; sekarang foto dikenali dari tampilannya. |
| `cabai kopay.webp` (S01, S02) | KNOWN Kopay → AUTO_LINK | OTHER → REVIEW_MISMATCH | Dari tampilannya model tidak yakin ini Kopay. Dulu ia ikut nama berkas; sekarang pertentangan itu dikirim ke peninjau manusia. |
| `daun cabai kopay.jpg` | Kopay (AUTO_LINK/UNCERTAIN) | Katokkon → REVIEW_MISMATCH, atau UNCERTAIN | Foto daun sulit dibedakan; nama berkas tidak lagi menutupi keraguan model. |
| commons `hungarian-wax_buah_081.jpg` | KNOWN → AUTO_LINK | OTHER → REVIEW_MISMATCH | Kasus yang sama: dulu tertaut karena nama berkas. |
| commons `cayenne_buah_080.jpg` | OTHER → CANDIDATE | KNOWN Hungarian Wax → AUTO_LINK (0.85) | Satu kesalahan visual baru, tepat di batas ambang. |

## Kesimpulan

1. **Celah M2 sudah tertutup.** Keputusan varietas tidak lagi bisa dikendalikan oleh nama berkas, dan pemeriksaan silang di fusi kini benar-benar membandingkan dua sinyal yang independen. Ini terlihat dari dua angka: model mengikuti nama berkas 30/40 → 2/40, dan AUTO_LINK salah 17 → 8 dari 120.
2. **Angka lama pada kondisi nama berkas BENAR tidak bisa dipakai sebagai ukuran kemampuan visual.** Kondisi NETRAL tidak berubah (4/19), dan itu adalah kemampuan visual yang sebenarnya pada foto PVT kartu tertutup.
3. **Biayanya:** foto yang benar tetapi tidak dikenali model kini masuk REVIEW_MISMATCH atau REVIEW_UNCERTAIN, sehingga tidak tertaut otomatis. Ini adalah perilaku yang diharapkan, karena kesalahan berpindah dari tautan salah yang diam-diam ke antrean tinjauan manusia. Akibatnya beban peninjau bertambah: pada PVT, REVIEW_* naik pada kondisi BENAR.
4. **Untuk Indonesia, hasil akhir yang dipakai pengguna (workbook gabungan) membaik** dari F1 0.960 menjadi 0.980.

## Batasan

- **Satu ulangan per set, dan model tidak deterministik.** Selisih kecil seperti commons 35 → 32, PVT terlihat 27 → 25, dan tertutup 4 → 3 berada di dalam CI 95%. Di set PVT foto ulang, yang nama berkasnya tidak relevan, 10 dan 4 jawaban tetap berubah antar-run. Untuk klaim statistik, jalankan ≥3 ulangan.
- **Gold atribut dan kunci sel P01 belum diverifikasi.**
- **Latensi provider (25-90 detik per foto) berbeda dari 7 Nov,** sehingga run dibagi menjadi 3 job paralel. Urutan foto tidak memengaruhi hasil.
- **Varietas di registri hanya dicocokkan oleh kode dari nama berkas.** Nama berkas yang menyebut varietas *tidak terdaftar* (kasus OTHER BENAR) belum dipakai sebagai sinyal CANDIDATE, sehingga sel itu turun dari 17/21 ke 3/21. Ini kandidat perbaikan berikutnya.

## Lokasi

- **Branch VPS `feat/vision-two-stage`** (belum di-commit):
  - `src/agents/vision_classification.py`
  - `src/agents/signal_fusion.py`
  - `src/integrations/vision_hook.py`
  - `tests/vision/test_two_stage_vision.py`
  - skrip di `data_evaluasi/skrip/`
- **Hasil:** `data_evaluasi/hasil_eksperimen/foto_two_stage_2026-11-12/`
  - `hasil/`: keluaran run;
  - `skor/`: skor run baru;
  - `skor_ablasi_fusi_lama/`: skor ablasi.
- **Tes:** semua tes vision lulus. Pada full suite, daftar tes yang gagal identik dengan sebelum perubahan; seluruhnya karena DB atau readiness, tidak ada yang terkait vision.
