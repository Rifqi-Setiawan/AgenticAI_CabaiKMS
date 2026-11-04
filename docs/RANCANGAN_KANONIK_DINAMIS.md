# Rancangan: skema kanonik dinamis (fase 2)

1 November 2026. Status: **tahap 1 sampai 3 diimplementasikan** (commit `b7b38e3`, `a5ebdb9`, `060b29f`; saklar `KMS_DYNAMIC_SCHEMA` mati bawaan); tahap 4 (eksperimen F2) berjalan, protokolnya di `SKENARIO_EKSPERIMEN.md` bagian 14. Menggantikan batasan fase 1 (katalog hanya di lapisan dokumen KMS). Dasar: pembacaan `canonical.py`, `indexing.py`, `output_builder.py`, `pipeline_runner.py`, `attribute_policy.py` pada commit `27e68bc`.

## 1. Tujuan (dari peneliti)

1. Atribut masukan yang di luar kanonik awal ikut menjadi **baris kanonik** untuk semua run berikutnya, sehingga sistem fleksibel untuk akuisisi atribut.
2. **Tanpa duplikat:** atribut bernama berbeda tetapi bermakna sama disatukan menjadi satu baris.
3. **Keluaran Excel tetap persis seperti sekarang** untuk baris kanonik awal; bila ada atribut baru, **baris bertambah**.

## 2. Yang dipelajari dari kode

| Hal | Fakta |
|---|---|
| Definisi baris kanonik | `CanonicalSchema.from_template()` membaca `template_kanonik.xlsx` (60 baris) dan tiga YAML (`row_keys`, `row_domains`, `row_aliases`). Setiap baris punya `id` posisional (`r_1`..`r_60`), `canonical_key`, `label`, `domain`, contoh, alias |
| Pemetaan | Retrieval Chroma (top-k dari seluruh baris) lalu rerank LLM, lalu verifier. Atribut tanpa padanan keluar sebagai NULL |
| Indeks | Satu koleksi Chroma bersama (`ensure_indexed`); bila jumlah baris atau hash representasi berubah, **seluruh koleksi dihapus dan dibangun ulang** |
| Keluaran Excel | `CanonicalOutputBuilder` mengisi satu baris per `schema.rows`; tidak ada baris lain |
| Fingerprint evaluasi | memuat `schema_version`, `template_hash`, hash prompt verifier; baris tambahan akan mengubahnya |

Akibat desain: menambah baris di **akhir** daftar menjaga id lama dan urutan Excel lama; menyisipkan di tengah akan menggeser id, indeks, dan hasil lama.

## 3. Rancangan

### 3.1 Skema = template + ekstensi persisten

- Tabel katalog ekstensi (migrasi 0006, sudah ada) dilengkapi kolom yang dibutuhkan pemetaan: `domain`, contoh nilai, alias, `status`, `seq` (urutan penambahan).
- `CanonicalSchema.from_template(extensions=...)` menambahkan baris ekstensi **setelah** 60 baris template, dengan id `r_61`, `r_62`, ... berurutan `seq`. Id baris yang sudah ada tidak berubah.
- Saklar `KMS_DYNAMIC_SCHEMA` (**mati secara bawaan**). Mati = identik dengan sistem yang dievaluasi. Hidup = skema memuat ekstensi dan fingerprint mencantumkan `extension_hash`.

### 3.2 Pemetaan dan penyatuan makna (anti duplikat)

Penyatuan terjadi di tiga tempat, berurutan:

1. **Saat pemetaan.** Karena baris ekstensi ada di indeks, atribut baru dengan nama lain tetapi makna sama otomatis dipetakan ke baris yang sudah ada (retrieval + rerank + verifier yang sama). Ini mekanisme utama.
2. **Saat mengusulkan baris baru.** Atribut yang tetap NULL menjadi *kandidat baris baru*. Sebelum dibuat, kandidat dibandingkan dengan seluruh baris dan alias (kemiripan embedding dan penilai LLM "apakah dua atribut ini bermakna sama?"). Bila sama, kandidat dijadikan **alias** baris itu; bila tidak, dibuat baris baru.
3. **Dalam satu run.** Kandidat baru yang saling bermakna sama (mis. "Kadar capsaicin" dan "Capsaicin content") dikelompokkan dulu, satu baris per kelompok.

Penyatuan setelahnya (kurator menemukan dua baris bermakna sama) dilakukan dengan **penggabungan**: baris yang kalah ditandai `merged_into` dan menjadi alias; id lama tetap ada di data lama agar riwayat tidak putus.

### 3.3 Penjaga kualitas (agar kolom sampah tidak menjadi kanonik)

- Daftar kolom identitas dan metadata yang tidak pernah diakuisisi (nomor urut, lokasi, koordinat, varietas, catatan bebas) dipakai bersama dengan penilai LLM "apakah ini karakter tanaman atau lingkungan yang dapat diukur?".
- Syarat minimum: kolom punya nilai pada sebagian baris data, bukan hanya header.
- Status baris baru: `provisional` (muncul di keluaran Excel dengan label baris yang sama, dapat digabung atau dibuang kurator) lalu `approved`. Catatan: status tidak mengubah tampilan Excel.

### 3.4 Indeks Chroma

Koleksi untuk skema ekstensi **terpisah** dari koleksi template (nama koleksi memuat `extension_hash`), supaya run evaluasi (saklar mati) tidak memicu pembangunan ulang yang saling menimpa. Penambahan satu baris cukup meng-upsert baris itu.

### 3.5 Keluaran Excel

`CanonicalOutputBuilder` tetap memakai `schema.rows`. Dengan ekstensi, 60 baris awal identik dalam isi dan urutan, ditambah baris ekstensi di bawah. Kolom Nomor dan Karakter, varietas, dan sel tidak berubah bentuk. Ada uji: keluaran saklar mati harus identik byte-per-sel dengan keluaran lama.

### 3.6 Hubungan dengan fase 1

Katalog persisten fase 1 tetap menjadi sumber kebenaran atribut. Fase 2 menambahkan: kolom domain dan contoh, pembacaan oleh `CanonicalSchema`, serta aliran akuisisi pada tahap pemetaan (bukan hanya pada draf dokumen). Penulisan ke dokumen KMS tetap hanya untuk tata letak Resume Data (opsi A).

## 4. Dampak pada evaluasi yang ada

| Komponen | Dengan saklar mati | Dengan saklar hidup |
|---|---|---|
| Mapping F1, recall atribut baru, foto | tidak berubah (dijaga uji regresi identik) | berubah menurut isi ekstensi; **bukan** bagian skor inti, dilaporkan sebagai eksperimen terpisah |
| Fingerprint | sama | memuat `extension_hash` |

## 5. Evaluasi fitur (eksperimen baru)

Berurutan, tanpa gold baru untuk metrik inti:

| Uji | Cara | Ukuran |
|---|---|---|
| F2-1 Akuisisi | Jalankan N07 dengan skema ekstensi kosong; kandidat baru dibuat otomatis | jumlah baris baru; proporsi kandidat yang benar-benar karakter tanaman (periksa manual) |
| F2-2 Penggunaan ulang | Jalankan N09 dan N08 sesudahnya | persentase atribut yang sebelumnya NULL sekarang terpetakan ke baris ekstensi; ketepatannya terhadap gold silang dataset |
| F2-3 Anti duplikat | Pasangan atribut sinonim dari gold silang dataset | presisi dan recall penyatuan; jumlah baris duplikat yang lolos |
| F2-4 Keutuhan Excel | Bandingkan keluaran saklar mati dengan keluaran lama | identik sel-per-sel |
| F2-5 Stabilitas | Ulangi urutan run 3 kali | variasi jumlah baris baru dan penyatuan antar pengulangan |

Gold silang dataset (atribut mana yang sama makna lintas N07, N08, N09, R02) perlu disusun; daftar pendek, dapat diturunkan dari gold yang ada dan diverifikasi peneliti.

## 6. Risiko

| Risiko | Mitigasi |
|---|---|
| Pencemaran skema oleh kolom bukan atribut | penjaga 3.3, status `provisional`, kurator dapat membuang atau menggabung |
| Duplikat makna lolos | penyatuan tiga tahap, penilai LLM, penggabungan retroaktif lewat alias |
| Perubahan skema mengganggu hasil lama | saklar mati bawaan, koleksi Chroma terpisah, fingerprint, uji regresi identik |
| Urutan run memengaruhi skema (jalur bergantung data) | catat urutan; F2-5 mengukur variasi; reset skema ekstensi antar eksperimen |
| Biaya pemanggilan LLM bertambah (penilai kemiripan) | hanya untuk kandidat NULL, dengan cache keputusan per label |
| Dampak ke dokumen KMS lama | hanya menambah atribut; id lama tetap; penggabungan memakai alias, bukan penghapusan |

## 7. Tahapan dan perkiraan

| Tahap | Isi | Perkiraan |
|---|---|---|
| 1 | Migrasi 0007 (kolom domain, contoh, alias, status, seq), `CanonicalSchema` dengan ekstensi, saklar, koleksi Chroma terpisah, uji keutuhan Excel | 1,5 hari |
| 2 | Aliran kandidat baru di pemetaan, penjaga kualitas, penyatuan tiga tahap (penilai LLM), cache | 2 hari |
| 3 | UI kurator: tinjau `provisional`, gabung, buang | 1 hari |
| 4 | Uji regresi identik (saklar mati) pada R01, N09, S01; eksperimen F2-1 sampai F2-5; tabel hasil | 1,5 hari |
| Total | | sekitar 6 hari kerja |

## 8. Keputusan yang diperlukan

1. **Persetujuan.** Baris baru langsung berstatus `provisional` dan ikut ke Excel pada run itu (otomatis), atau menunggu persetujuan kurator sebelum muncul di Excel? (Rancangan di atas: otomatis `provisional`, kurator dapat menggabung atau membuang; ini sesuai tujuan "atribut baru ikut menjadi kanonik".)
2. **Posisi baris baru di Excel.** Ditambah di akhir (disarankan, menjaga id dan hasil lama), atau dikelompokkan menurut domain pada tampilan (hanya urutan tampilan, id tidak berubah)?
3. **Aturan penyatuan.** Otomatis bila penilai LLM dan kemiripan embedding sepakat di atas ambang tertentu, sisanya diserahkan ke kurator? Atau semua penyatuan wajib disetujui kurator?
4. **Cakupan data.** Akuisisi berlaku untuk semua format workbook pada tahap pemetaan (ya, karena pemetaan sudah berjalan untuk semuanya), sementara penulisan dokumen KMS tetap hanya Resume Data (opsi A).
5. **Izin** mengubah kode produksi (migrasi 0007, restart) dengan pencatatan deviasi D9, dan eksperimen F2 dijalankan pada database terpisah.
