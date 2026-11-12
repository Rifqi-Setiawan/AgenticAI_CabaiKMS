# Hasil sementara eksperimen CABAI-KMS (1 November 2026)

> **USANG.** Angka terbaru (atribut 8 Nov, foto 12 Nov 2026; data level varietas, bge-m3, deskripsi varietas untuk model
> visi, model visi buta nama berkas D24) ada di
> `docs/SKOR METRIKS EVALUASI.md` dan `docs/PANDUAN_EKSPERIMEN_LENGKAP.md` Bagian 6A.
>
> **USANG (4 Nov 2026).** Dokumen ini arsip. Angka foto Commons di bawah masih memuat 19 jawaban mock (macro-F1 0,692, AUTO_LINK 67/94). Angka terbaru dan terkoreksi ada di `docs/PANDUAN_EKSPERIMEN_LENGKAP.md` (macro-F1 0,640, Top-1 0,727, AUTO_LINK 64/87 = 0,736).

**Status: sementara.** Semua skor dihitung terhadap **gold sementara**, belum gold dua anotator (buta + adjudikasi). Jangan dikutip sebagai hasil akhir.
Commit: atribut `323f1e4` (harness `24e1037`+D1 sampai D5), foto `bc3c21b`. Deviasi D1 sampai D6: bagian 12 `SKENARIO_EKSPERIMEN.md`.
Data mentah: `data_evaluasi/hasil_eksperimen/` (RUNLOG, `SHA256SUMS`).

## 1. Pemetaan atribut (harness 3 pengulangan; UI 1 run; hasil identik)

| Varian | Precision | Recall | Mapping F1 | Recall atribut baru |
|---|---|---|---|---|
| S4 sistem penuh (R01, R02, N07, N09) | 0,984 | 0,861 | 0,919 | 0,993 |
| S1 exact-name | 1,000 | 0,417 | 0,588 | 1,000 |
| S2 retrieval top-1 | 0,253 | 0,694 | 0,370 | 0,100 |

Semua dataset lewat UI (S4): semua 0,945 (S1 0,422); R 0,974; N 0,971; S 0,915. Per dataset: N07 0,974; N08* 0,875; N09 1,000; R01 0,667 (1 butir bertarget); R02 1,000; S01 0,974; S02 1,000; S03 0,783.
S04 dan N08 asli ditolak sistem ("Struktur workbook belum dapat diproses"), dilaporkan sebagai kasus penolakan, bukan skor. *N08 memakai berkas varian (kolom A1 `Variety`, deviasi D4).
Variasi antar tiga pengulangan atribut: skor agregat identik (simpangan baku 0), tetapi pada tingkat butir ada variasi kecil (satu butir pada N09 berbeda antar pengulangan; teks alasan model berbeda pada sekitar 69 dari 80 baris). Model tidak deterministik, namun pergeserannya tidak mengubah skor pada dataset yang diuji.

## 2. Foto Commons (160 foto, 8 run UI, gold sementara)

| Varian | Macro-F1 (CI 95%) | Top-1 pada KNOWN (CI 95%) |
|---|---|---|
| V3 fusi (status akhir = status visual) | 0,692 (0,589 sampai 0,778) | 0,758 (0,667 sampai 0,837) |
| V1 hanya gambar | 0,692 | 0,758 |
| V2 hanya nama file | 0,314 (0,265 sampai 0,360) | 0,394 (0,299 sampai 0,486) |
| V3b (review dihitung UNCERTAIN) | 0,618 (0,537 sampai 0,698) | 0,677 (0,581 sampai 0,760) |

Split test (108 foto): macro-F1 0,667; Top-1 0,768. Split val (52): 0,733; 0,733.
Per kondisi nama file (V3): INFORMATIF 0,875 / 0,974; NETRAL 0,583 / 0,725; MENYESATKAN 0,532 / 0,400.

Matriks V3 (gold ke prediksi): KNOWN: 87 KNOWN, 7 OTHER, 5 UNCERTAIN. OTHER: 16 KNOWN, 29 OTHER. UNCERTAIN: 3 KNOWN, 5 OTHER, 8 UNCERTAIN.
Aksi fusi: AUTO_LINK 94, CANDIDATE 32, REVIEW_MISMATCH 21, REVIEW_UNCERTAIN 13. Ketepatan AUTO_LINK 67/94 = 0,71 bila status dan varietas harus benar (0,84 bila hanya status; lihat `analisis_lanjut.md`, bagian 5).

Catatan H3: pada pemetaan V3 yang dipakai, V3 identik dengan V1, jadi tidak ada bukti fusi menaikkan macro-F1. Fusi mengalihkan 20 foto kondisi MENYESATKAN ke review (11 di antaranya sebenarnya benar). H3 **tidak didukung** oleh data ini; manfaat fusi lebih tepat dibaca sebagai pencegahan tautan otomatis yang salah (analisis eksploratori). Pada kondisi MENYESATKAN, 11 foto tertaut otomatis dan 0 di antaranya benar (status dan varietas), sedangkan 21 dialihkan ke review dengan 12 sebenarnya benar.

## 3. Foto Indonesia, 4 kombinasi spreadsheet + Drive 1 (10 foto dinilai per kombinasi)

| Kombinasi | Sebelum D6 (`323f1e4`) | UI sesudah D6 | Harness 4 pengulangan (rata-rata ± SD) |
|---|---|---|---|
| S01 | 2/10 | 7/10 | 7,2 ± 0,43 |
| S02 | 2/10 | 8/10 | 7,8 ± 0,43 |
| S03 | 2/10 | 5/10 | 5,8 ± 0,43 |
| S04 | ditolak | ditolak | tidak dijalankan |

Satu foto per kombinasi tidak konsisten antar pengulangan. Foto Katokkon benar di semua run.

## 4. Uji signifikansi dan stratifikasi (`data_evaluasi/hasil_eksperimen/analisis_lanjut.md`, bootstrap berpasangan 10.000 ulangan, Holm)

| Perbandingan | Himpunan | Selisih | CI 95% | p Holm |
|---|---|---|---|---|
| S4 vs S1, Mapping F1 | held-out | +0,357 | +0,258 sampai +0,476 | < 0,0001 |
| S4 vs S2, Mapping F1 | held-out | +0,602 | +0,528 sampai +0,676 | < 0,0001 |
| S4 vs S2, recall atribut baru | held-out | +0,978 | +0,950 sampai +1,000 | < 0,0001 |
| V3 vs V2, macro-F1, nama file MENYESATKAN (n=32) | foto | +0,276 | +0,006 sampai +0,497 | 0,088 (tidak signifikan) |
| V3 vs V2, macro-F1, semua foto | foto | +0,378 | +0,272 sampai +0,474 | < 0,0001 |
| V3 vs V1, macro-F1 | foto | 0 | 0 | tidak bermakna (identik) |

Mapping F1 S4: held-out 0,978 (0,950 sampai 1,000); dev 0,909 (0,852 sampai 0,953). Dev tidak lebih tinggi dari held-out, jadi tidak ada tanda overfit ke data pengembangan.
Per stratum: butir yang dapat diselesaikan lookup (38 butir) dijawab sempurna oleh S4 dan S2, jadi tidak membedakan varian. Pada butir semantik (104 bertarget, 157 tanpa target): S4 F1 0,923 (0,884 sampai 0,957), S2 0,234 (0,176 sampai 0,290). Klaim keunggulan S4 bertumpu pada stratum semantik.
RQ1, RQ2: didukung. RQ3: tidak didukung (V3 = V1; keunggulan V3 atas V2 pada MENYESATKAN tidak signifikan setelah Holm). RQ4 (recall OTHER V3 vs V1): tidak dapat didukung, lihat bagian 12. RQ5: didukung (UI = harness pada atribut; foto kombinasi dalam rentang).

## 5. Keterbatasan yang berlaku

- Gold sementara; 57 butir perlu adjudikasi; kappa antar anotator belum ada.
- Foto Commons adalah proksi luar negeri; kelas kecil tidak dilaporkan per kelas.
- Dev dan held-out sudah dipisah (bagian 4), tetapi alias `row_aliases.yaml` berasal dari data dev dan 25% butir bertarget dapat diselesaikan lookup; klaim bertumpu pada stratum semantik.
- Baseline S3 hanya aproksimasi (penilai melihat seluruh 60 baris, bagian 12) dan hanya pada dataset atribut tunggal; RQ4 diuji tetapi tidak dapat didukung (V3 dan V1 identik).
- Penulisan dokumen KMS (commit PostgreSQL) hanya berlaku untuk tata letak Resume Data; delapan format lain berhenti di Excel kanonik (keputusan opsi A). Evaluasi pemetaan dan foto tidak bergantung pada batas ini; uji fitur atribut baru hanya pada tata letak tersebut.
- Antrean kandidat tidak direset antar run UI Bagian C (36 kandidat setelah run); foto Commons berbeda dari foto Drive 1, jadi efeknya diperkirakan kecil, belum diverifikasi.

## 6. Skor foto terhadap gold hasil tinjauan visual (1 November 2026)

Gold foto ditinjau ulang satu per satu secara visual (bukan verifikasi ahli botani). Aturan: label sumber dipertahankan bila foto konsisten dan buah terlihat jelas; diubah ke UNCERTAIN bila hanya bunga, tanaman, bibit, atau buah tidak dikenali, atau label sumber saling bertentangan; dikeluarkan bila bukan foto cabai.
Hasil: 158 foto masuk (2 dikeluarkan), 23 label diubah (14,6%): 22 menjadi UNCERTAIN, 1 UNCERTAIN menjadi KNOWN Paprika. Kelas: KNOWN 83, OTHER 40, UNCERTAIN 35. Berkas: `gambar/manifest/gold_gambar_manifest_final.csv`; catatan per foto ada di kolom `catatan_tinjauan`.

| Varian | Macro-F1 (CI 95%) | Top-1 KNOWN (CI 95%) |
|---|---|---|
| V3 fusi | 0,614 (0,525 sampai 0,691) | 0,807 (0,720 sampai 0,882) |
| V1 hanya gambar | 0,614 | 0,807 |
| V2 hanya nama file | 0,353 (0,300 sampai 0,403) | 0,410 (0,310 sampai 0,513) |

Split test (107 foto): macro-F1 0,585; Top-1 0,807. Per kondisi nama file (V3): INFORMATIF 0,760 / 1,000; NETRAL 0,554 / 0,806; MENYESATKAN 0,360 / 0,412.
Matriks V3 (gold ke prediksi): KNOWN: 74 KNOWN, 6 OTHER, 3 UNCERTAIN. OTHER: 13 KNOWN, 27 OTHER. UNCERTAIN: 19 KNOWN, 7 OTHER, 9 UNCERTAIN.
Temuan: sistem hampir tidak menahan keputusan pada foto yang secara visual tidak dapat dibedakan (19 dari 35 foto UNCERTAIN ditautkan ke satu varietas); ini menurunkan macro-F1, sementara Top-1 pada foto KNOWN naik. Skor ini menggantikan angka bagian 2 untuk foto.
Keterbatasan: tinjauan visual tidak dapat membedakan banyak varietas cabai dengan pasti (banana pepper vs Hungarian Wax, habanero vs scotch bonnet); keputusan banyak bertumpu pada label sumber Commons.

## 7. Uji fitur atribut baru jadi kanonik (E-A1 sampai E-A3), 1 November 2026

Uji fungsi pada database terpisah `cabai_kms_eval`, memakai kode produksi commit `a16c5cc`. Masukan sintetis: `data_input.xlsx` (format Resume Data) ditambah lima kolom atribut baru dengan 13 baris; kurator disimulasikan oleh kunci jawaban yang ditetapkan sebelum run (`skrip/eval_atribut_baru.py`). Ini bukti fungsi, bukan uji generalisasi. Hasil mentah: `hasil_eksperimen/hasil_atribut_baru/2026-11-01/`.

| Uji | Hasil |
|---|---|
| E-A1 deteksi | 5 dari 5 label baru terdeteksi sebagai NEW_ATTRIBUTE (65 sel); tidak ada label lain salah ditandai |
| E-A1 keputusan | 3 `REGISTER_NEW`, 1 `MAP_TO_EXISTING` (alias ke tinggi tanaman), 1 `REJECT`; satu keputusan menyelesaikan seluruh sel berlabel sama (44 disetujui, 21 ditolak: 13 sel catatan surveyor dan 8 sel pada dokumen dengan nilai bertentangan antar baris) |
| E-A1 commit | berhasil: 9 dokumen dibuat, 57 atribut; baris katalog 3, alias 1, penolakan 1 |
| E-A2 penggunaan ulang | run 2 memuat 5 label lama dan 2 label baru: 5 dari 5 label lama dikenali otomatis (100%, 0 ditanyakan ulang); hanya 2 label baru ditanyakan (26 sel, turun dari 65 sel pada run 1) |
| E-A2 duplikat | label "Kadar Capsaicin Total" ditandai mirip "Kadar Capsaicin (ppm)" (kemiripan 0,762) pada item review |
| E-A3 keutuhan | atribut dokumen empat dokumen naik 8 menjadi 12 (3 atribut baru + 1 alias); dokumen dengan nilai bertentangan antar baris tidak ditulis; catatan surveyor tidak tersimpan; atribut baru berresolusi HUMAN_REVIEW dengan jejak sumber |
| E-A3 keamanan | `DELETE` pada katalog ditolak (append-only); commit ulang idempoten (replayed) |

Temuan sampingan:
1. Planner dokumen KMS hanya memahami tata letak "Resume Data" (`data_input.xlsx`). Delapan workbook lain (D01 sampai D04, N07, N08, N09, R02, workbook varietas terdaftar) menghasilkan 0 dokumen dengan review LOCATION_UNRESOLVED dan PLANT_IDENTITY_UNRESOLVED. Tahap pemetaan atribut berjalan untuk semuanya, tetapi penulisan ke dokumen varietas-lokasi hanya untuk satu tata letak. Fitur atribut baru karena itu hanya teruji pada tata letak tersebut.
2. `get_or_plan_draft` (halaman Hasil) memakai `data/samples/data_input.xlsx` sebagai cadangan bila berkas run tidak ditemukan; draf KMS yang tampil dapat berasal dari workbook lain daripada yang dijalankan (teramati Jarvis pada pilot S01).
Keterbatasan: data sintetis, kurator simulasi, satu tata letak, tanpa perbandingan dengan baseline.

## 8. Skema kanonik dinamis, uji asap saklar hidup (1 November 2026)

Konfigurasi: `KMS_DYNAMIC_SCHEMA=true`, API terpisah (port 18095) dengan database `cabai_kms_eval` yang kosong, model teks produksi, commit `a5ebdb9`. Masukan `data_input.xlsx` (R01). Hasil mentah: `hasil_eksperimen/hasil_dinamis/`.

| Run | Hasil |
|---|---|
| Run 1 (skema 60 baris) | 8 atribut tanpa padanan dinilai penilai akuisisi, 8 menjadi baris baru (klorofil daun, nitrogen daun, kelembaban permukaan daun, suhu permukaan daun, kelembaban tanah, pH tanah, suhu udara, kelembaban udara); kolom identitas (nomor, koordinat, ketinggian, lokasi) tidak diakuisisi; Excel 61 menjadi 69 baris, 60 baris awal tidak berubah; `schema_version` menjadi `...+ext.fd88571c0003` |
| Run 2 (ulang R01, skema 68 baris) | 0 akuisisi; 7 atribut dipetakan ke baris baru lewat retrieval dan 1 (pH tanah) lewat exact-name; DB tetap 8 baris; Excel 69 baris dengan nilai terisi |

Ini bukti fungsi pada satu dataset. Eksperimen terstruktur (akuisisi N07, penggunaan ulang N09 dan N08, penyatuan sinonim terhadap gold silang dataset, stabilitas tiga pengulangan) belum dijalankan. Catatan: 8 baris baru bergantung pada penilai LLM; "Humidity (%)" pada konteks daun menjadi "kelembaban permukaan daun", penamaan yang perlu ditinjau kurator.

## 9. Eksperimen F2 versi 1 (skema kanonik dinamis, 1 November 2026)

Konfigurasi: saklar hidup, API dan database terpisah, commit `060b29f`; urutan R01, N07, N09, R02; tiga pengulangan dari database kosong; model teks produksi. Data mentah: `hasil_eksperimen/hasil_dinamis/urutan_A/`; analisis: `hasil_eksperimen/analisis_kanonik_dinamis_v1.md`.

**F2-1 dan F2-2 (tiga pengulangan, rentang):**

| Dataset | Atribut | Kandidat dinilai | Baris baru | Bukan karakter | Duplikat (tak ditulis) | Dipetakan ke baris akuisisi lama |
|---|---|---|---|---|---|---|
| R01 (pertama) | 13 | 8 | 8 | 0 | 0 | 0 |
| N07 | 69 | 49 | 37 sampai 41 | 8 sampai 11 | 0 sampai 1 | 0 |
| N09 | 80 | 15 sampai 23 | 6 sampai 13 | 8 | 1 sampai 2 | 32 sampai 42 |
| R02 | 53 | 9 sampai 10 | 1 sampai 2 | 8 | 0 sampai 1 | 26 |

Total baris akuisisi akhir 43, 45, dan 43 (Excel 104 sampai 106 baris). Dataset berikutnya memakai ulang baris lama secara luas (N09: 32 sampai 42 atribut; R02: 26), dan jumlah baris baru turun tajam (R02 hanya 1 sampai 2 baris baru). Penilai menolak atribut administrasi dan silsilah (Asal, Silsilah, Golongan varietas, Pemohon, Pemulia, Peneliti, Varietas Cabai) sebagai bukan karakter.

**F2-4 keamanan (Mapping F1 baris template, rata-rata 3 pengulangan):** R01 0,667 (selisih 0,000), N07 0,974 (0,000), N09 0,978 (-0,022), R02 0,981 (-0,019). Versi ketat (baris akuisisi dihitung salah positif pada butir NO_MATCH) jauh lebih rendah (0,18 sampai 0,59), sesuai dugaan karena atribut baru memang tidak ada di gold.

**F2-3 dan F2-5, temuan yang merugikan:**
1. **Duplikat dengan template.** Pada pengulangan 2, "Mahkota" (N07) diakuisisi sebagai baris baru `warna mahkota bunga` padahal template sudah punya `warna mahkota`. Baris itu kemudian merebut empat pemetaan butir bertarget pada N09 dan R02 (Warna mahkota bunga, Warna bunga, Mahkota) dari template; inilah penyebab selisih F1 -0,022 dan -0,019. Penilai hanya melihat empat baris terdekat dari retrieval, bukan seluruh daftar baris.
2. **Duplikat antar baris akuisisi (kasus batas):** `tebal daging buah` bersama `tebal perikarp buah` (pengulangan 2), `panjang buah` dan `posisi buah` yang lebih umum daripada baris template bertahap. Pasangan label dengan kemiripan tinggi lainnya (kelembapan tanah dan udara, diameter batang dan buah, penyakit dan hama, penampang buah dan daun) adalah atribut berbeda, bukan duplikat.
3. **Duplikat yang dikenali tetapi tidak dipetakan.** Tiga atribut per pengulangan dinilai sama dengan baris yang ada (mis. "Umur mulai panen (hari)", "Fruit shape") tetapi nilainya tidak ditulis ke baris itu, sehingga data hilang; pada R02 pengulangan 1 ini menghilangkan satu pemetaan template yang benar ("Fruit shape").
4. **Stabilitas rendah.** Kemiripan himpunan label antar pengulangan Jaccard 0,57 sampai 0,66 (variasi penamaan dan batas akuisisi). Jumlah baris stabil (43 sampai 45).

Dua perbaikan diterapkan sebelum versi 2 (deviasi D9d): penilai menerima daftar seluruh baris yang ada beserta aturan makna sama yang lebih ketat, dan atribut berstatus duplikat ditulis ke baris yang ada (status `MERGED_TO`). Hasil versi 2 di bagian 10.

Keterbatasan: satu urutan dataset, tinjauan kualitas baris oleh model (sebagian besar baris adalah karakter tanaman yang sah, mis. diameter batang, warna benang sari, bobot 1000 biji, tinggi dikotomus), belum diverifikasi peneliti.

## 10. Eksperimen F2 versi 2 (setelah perbaikan D9d; sebagian tidak sah)

Konfigurasi sama dengan versi 1 (commit `3705aab`); data: `hasil_eksperimen/hasil_dinamis/urutan_B/`; analisis: `hasil_eksperimen/analisis_kanonik_dinamis_v2.md`.

**Dua belas run, tetapi lima di antaranya tidak menilai atribut sama sekali:** penilai akuisisi memproses seluruh kandidat dalam satu panggilan (sampai 55 atribut dengan daftar seluruh baris), panggilan itu memakan 2 sampai 3 menit dan sering kehabisan waktu
(`LLMCallError`; terbukti pada pengulangan manual 121 detik gagal, 161 detik berhasil). Pada run yang gagal akuisisi dilewati tanpa menggugurkan run (49 sampai 55 kandidat berstatus FAILED: pengulangan 1 N07 dan N09, pengulangan 3 N07, N09, R02).
Karena itu angka gabungan versi 2 (jumlah baris akhir 35, 39, dan 8; Jaccard 0,09 sampai 0,51; F1 template tidak berubah) **tidak boleh dibaca sebagai hasil fitur**; hanya pengulangan 2 yang lengkap tanpa kegagalan.

**Pengulangan 2 (lengkap, 0 kegagalan):**

| Dataset | Kandidat | Baris baru | Digabung ke baris ada | Bukan karakter | Dipetakan ke baris akuisisi lama |
|---|---|---|---|---|---|
| R01 | 8 | 8 | 0 | 0 | 0 |
| N07 | 49 | 39 | 1 | 9 | 0 |
| N09 | 19 | 6 | 5 | 8 | 36 |
| R02 | 12 | 0 | 4 | 8 | 23 |

Total 39 baris akuisisi (Excel 100 sampai 106 baris dari 60). Atribut yang dinilai sama dengan baris yang ada kini ditulis ke baris itu (MERGED_TO: 1 pada N07, 5 pada N09, 4 pada R02), tidak lagi hilang. R02 tidak membuat baris baru sama sekali. Pasangan label mirip yang tersisa hanya atribut yang berbeda (kelembapan tanah dan udara, diameter batang dan buah, penyakit dan hama).
Satu pengulangan tidak cukup untuk menilai stabilitas; versi 3 mengulang eksperimen setelah perbaikan batching (D9e).

## 11. Eksperimen F2 versi 3 (hasil yang dipakai; commit `6217420`)

Konfigurasi: saklar hidup, API dan database terpisah, urutan R01, N07, N09, R02, tiga pengulangan dari database kosong, penilai dalam batch 12 dengan percobaan ulang (D9e). **Tidak ada run yang gagal** (0 kandidat FAILED pada 12 run). Data: `hasil_eksperimen/hasil_dinamis/urutan_C/`; analisis: `hasil_eksperimen/analisis_kanonik_dinamis_v3.md`.

**F2-1 dan F2-2** (identik pada ketiga pengulangan, kecuali N09 15 sampai 17 kandidat):

| Dataset | Atribut | Kandidat dinilai | Baris baru | Digabung ke baris ada | Bukan karakter | Dipetakan ke baris akuisisi lama | Baris Excel |
|---|---|---|---|---|---|---|---|
| R01 | 13 | 8 | 8 | 0 | 0 | 0 | 69 |
| N07 | 69 | 49 | 28 | 13 | 8 | 0 | 97 |
| N09 | 80 | 16 sampai 17 | 4 | 4 sampai 5 | 8 | 39 | 101 |
| R02 | 53 | 11 | 0 | 3 | 8 | 24 | 101 |

Akhir tiap pengulangan: **40 baris akuisisi** (Excel 60 menjadi 101 baris); 84 sampai 85 atribut tanpa padanan menjadi 40 baris, jadi sekitar 53% kandidat disatukan atau dipakai ulang. Dataset ketiga dan keempat hampir tidak membuat baris baru (N09 4, R02 0) karena atributnya sudah terwakili.

**F2-3 anti duplikat.** Tidak ada baris akuisisi yang menggandakan baris template (`warna mahkota bunga` pada versi 1 tidak muncul lagi). Pasangan label mirip yang tersisa hanya atribut berbeda (kelembaban tanah dan udara, diameter batang dan buah, ketahanan penyakit dan hama). Penggabungan yang patut ditinjau kurator: `Panjang dikotomus` digabung ke `tinggi dikotomus`, `Tipe berbuah` ke `posisi buah masak` (gold AMBIGUOUS), `Tebal daging buah` ke `tebal kulit buah`. Dari 19 penggabungan pada pengulangan 1, hanya 1 yang bertarget baris template dan dapat dinilai terhadap gold (benar); sisanya bertarget baris akuisisi sehingga gold tidak punya jawaban.

**F2-4 keamanan (Mapping F1 baris template, rata-rata 3 pengulangan):** R01 0,667 (selisih 0,000), N07 1,000 (+0,026), N09 1,000 (0,000), R02 1,000 (0,000). Pemetaan template tidak lebih buruk dibanding mode beku; kenaikan N07 berasal dari atribut yang tadinya NULL lalu ditulis ke baris template (bukan klaim kemampuan: n kecil). F1 versi ketat 0,18 sampai 0,61 sesuai dugaan (atribut baru tidak ada di gold).

**F2-5 stabilitas.** Jumlah baris sama (40, 40, 40); kemiripan himpunan label Jaccard 0,70 sampai 0,78 (35 baris sama pada pasangan 1-2 dan 1-3; sisanya variasi penamaan, mis. kelembapan dan kelembaban). Versi 1: 43 sampai 45 baris, Jaccard 0,57 sampai 0,66.

**Kesimpulan terbatas.** Pada satu urutan dataset, mode adaptif mengakuisisi 40 baris kanonik dari 84 atribut tanpa padanan, memakai ulang dan menyatukan makna tanpa menurunkan pemetaan template, dengan hasil yang stabil antar pengulangan. Batas: satu urutan dan domain, penilai berbasis model, kualitas baris ditinjau model dan belum diverifikasi peneliti, penamaan baris bergantung model (variasi ejaan), dan tiga putaran perbaikan setelah mengamati hasil (D9d, D9e), sehingga hanya versi 3 yang layak dipakai untuk klaim; versi 1 dan 2 tetap dilaporkan sebagai evaluasi iteratif.

## 12. RQ4 dan baseline S3 (2 November 2026)

**RQ4** (`hasil_eksperimen/analisis_rq4.md`, skrip `skrip/analisis_rq4.py`): recall kelas OTHER pada 158 foto Commons (40 berlabel OTHER), hasil UI.

| Varian | Recall OTHER | CI 95% |
|---|---|---|
| V3 (fusi) | 0,675 | 0,525 sampai 0,816 |
| V1 (hanya gambar) | 0,675 | 0,525 sampai 0,816 |
| V2 (hanya nama file) | 0,000 | 0,000 sampai 0,000 |

V3 vs V1: selisih 0,000 (p Holm 1,0). **H4 tidak didukung**: V3 dan V1 identik pada pemetaan yang dipakai (tindakan fusi mempertahankan status visual), sehingga selisih nol menurut konstruksi. V2 tidak pernah menghasilkan OTHER karena hanya mencocokkan nama file ke varietas terdaftar (sifat varian, bukan temuan). Sebanyak 13 dari 40 foto OTHER diprediksi KNOWN, yaitu varietas di luar daftar yang ditautkan paksa ke varietas terdaftar.

**Baseline S3 (aproksimasi)** (`hasil_eksperimen/analisis_s3.md`, skrip `skrip/analisis_s3.py`; data `hasil_eksperimen/hasil_harness/2026-11-02_S3/`). Harness dengan opsi `--s3`: pipeline yang sama (termasuk pencocokan nama persis), tetapi penilai menerima seluruh 60 baris kanonik tanpa peringkat retrieval. Ini bukan LLM murni; yang diisolasi adalah penyempitan kandidat oleh retrieval. Dataset R01, R02, N07, N08 (berkas varian), N09; 222 butir; 3 pengulangan; kombinasi S01 sampai S03 tidak dijalankan. Percobaan pertama dengan `k=60` gagal seluruhnya (batas retrieval 5 sampai 10) dan dibuang; harness ditambah opsi `--s3`.

| Himpunan | S4 (retrieval, rep1) F1 | S3 F1 (identik pada 3 pengulangan) | Selisih S4 - S3 (CI 95%) | p Holm |
|---|---|---|---|---|
| Held-out (n=208) | 0,978 | 1,000 | -0,022 (-0,050 sampai 0,000) | 0,305 |
| Semua (n=222) | 0,972 | 0,993 | -0,021 (-0,049 sampai 0,000) | 0,283 |

Tiga butir berbeda, ketiganya sama di tiap pengulangan: `Mahkota` (N07), `Leaf shape` dan `Mature fruit colour` (N08). S4 tidak memetakan butir itu (retrieval tidak memasukkan baris benar ke kandidat), S3 memetakannya dengan benar. Tidak ada perbedaan signifikan.

**Pembacaan.** Dengan katalog hanya 60 baris, penilai yang melihat semua baris sama baiknya dengan sistem berbasis retrieval, bahkan sedikit lebih baik pada tiga butir. **Kontribusi retrieval terhadap akurasi tidak terbukti pada data ini**; pengamatan ini harus dilaporkan sebagaimana adanya. Keunggulan sistem atas S1 dan S2 (bagian 4) tetap berlaku, tetapi keunggulan retrieval atas baseline LLM tanpa retrieval tidak didukung. Retrieval kemungkinan lebih berguna pada katalog yang lebih besar (relevan dengan skema dinamis, 101 baris atau lebih) atau untuk biaya dan latensi: S3 memakan 85 sampai 580 detik per run, lebih lama dari S4 (perbandingan waktu belum dianalisis sistematis). Keterbatasan: butir S3 selalu identik antar pengulangan, jadi tidak ada informasi variasi.

## 13. Tabel kasus L3 (foto Indonesia, kualitatif)

Tabel lengkap per foto dan per spreadsheet: `data_evaluasi/hasil_eksperimen/tabel_kasus_l3.md` (skrip `skrip/tabel_kasus_l3.py`; hasil UI commit `bc3c21b`). Disajikan sebagai kasus, bukan F1 (n=10 per kombinasi). Status CANDIDATE di UI dihitung OTHER.

| Kombinasi | Cocok dengan harapan (status visual mentah) | Foto yang tidak cocok |
|---|---|---|
| S01 | 7 dari 10 | foto C. annuum (KNOWN Cabai tanjung, keyakinan 0,85; harapan UNCERTAIN); daun Gendot (dikenali Katokkon); foto C. chinense dan C. annuum (KNOWN Katokkon; harapan UNCERTAIN) |
| S02 | 8 dari 10 | foto C. annuum (KNOWN Kopay, 0,95); daun Gendot (dikenali Katokkon) |
| S03 | 6 dari 10 | foto C. annuum (KNOWN Cabai tanjung, 0,95); buah Domba (dinilai OTHER padahal pada S03 Domba terdaftar); daun Gendot (dikenali Katokkon padahal pada S03 harapan OTHER); foto C. chinense dan C. annuum (KNOWN Katokkon) |
| S04 | ditolak | struktur workbook tidak dapat diproses |

Pola yang sama di semua kombinasi: empat foto Katokkon dan buah Kopay selalu benar; kandidat OTHER (buah dan daun Domba pada S01 dan S02) dikenali sesuai harapan. Kegagalan berulang ada di dua tempat: (1) daun Gendot selalu dikenali sebagai Katokkon, dan (2) dua foto yang menurut gold tidak dapat dipastikan (jenis C. annuum, C. chinense) ditautkan ke varietas terdaftar dengan keyakinan 0,85 sampai 0,95; pada beberapa run tautan itu tertulis ke KMS (kolom Ditulis=True). Pola kedua adalah risiko tautan paksa yang relevan bagi RQ4.
Angka 7, 8, 5 di bagian 3 memakai status akhir V3 (foto yang dialihkan ke review dihitung UNCERTAIN); tabel L3 memakai status visual mentah, sehingga S03 berbeda satu foto (daun Domba: KNOWN Domba tetapi dialihkan ke review). Label foto berasal dari nama berkas peneliti; foto daun, bunga, dan tangkai tidak dapat dibedakan varietasnya dari gambar.

## 14. Anotasi ulang buta gold atribut (3 November 2026)

Subset 100 butir (57 prioritas `perlu_adjudikasi` + 43 acak terstratifikasi `gold_status`, seed 20261102; S04 tidak ikut), urutan diacak, tanpa gold, prediksi sistem, atau tanda prioritas (`data_evaluasi/anotasi_buta/subset_v1/`, skrip `skrip/buat_subset_anotasi_buta.py`).
Diisi oleh penulis, sehari setelah memverifikasi gold. Skor: `skrip/skor_anotasi_buta.py`, laporan `anotasi_buta/subset_v1/hasil/laporan_kappa.md`.

| Himpunan | n | Sepakat longgar | Kappa label | Kappa biner |
|---|---|---|---|---|
| Semua | 100 | 0,980 | 0,974 | 0,960 |
| Prioritas | 57 | 0,982 | 0,977 | 0,965 |
| Acak | 43 | 0,977 | 0,969 | 0,953 |

Estimasi tertimbang seluruh gold (318 butir): longgar 0,978 (CI 95% 0,936 sampai 1,000). Beda target hanya 2 butir (B035 Corolla diameter, B078 Penciri utama), keduanya ditandai Ragu; 5 butir beda status AMBIGUOUS/COMPOSITE atau kunci tambahan saja.
**Pembacaan:** ini konsistensi pelabelan peneliti yang sama, bukan validitas independen (pengisi juga memverifikasi gold sehari sebelumnya). Anotator independen (pakar domain) tetap dibutuhkan untuk klaim gold manusia.

## 15. Analisis tambahan untuk paper (2 November 2026)

`data_evaluasi/hasil_eksperimen/analisis_paper.md` (skrip `skrip/analisis_paper.py`; dump retrieval tanpa LLM `skrip/dump_retrieval.py`, top-1 identik dengan harness 312/312).
S2+tau (tau 0,386, dituning di dev): F1 held-out 0,460; S4 vs S2+tau +0,518 (p Holm < 0,001). Retrieval pada 104 butir semantik bertarget: Hit@1 0,404, Hit@8 0,779, Hit@semua kandidat 0,865 = recall S4; ke-14 kesalahan S4 semuanya retrieval meleset dan reranker memilih NULL. Latency median total S4 1573 s vs S3 1511 s.
Penerimaan: 129 AUTO_ACCEPT, 128 benar (0,992); 164 REVIEW (56%), 150 di antaranya gold NO_MATCH. Foto (label sumber): ketepatan AUTO_LINK nama file netral 29/44 = 0,659.
Draf paper IEEE: `docs/paper/` (PDF dan sumber LaTeX); sumber utama di VPS `/srv/hermes-control/personal/paper-cabai-kms/`.
