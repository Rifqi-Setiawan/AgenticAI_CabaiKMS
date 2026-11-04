# Rancangan: atribut baru menjadi kanonik untuk seluruh dokumen

1 November 2026. Status: **fase 1 diimplementasikan** (commit `a16c5cc`, 1 November 2026); rancangan disusun dari pembacaan kode di commit `bc3c21b`. Fase 2 (integrasi pemetaan dan indeks Chroma) belum dikerjakan.

## 1. Kondisi sekarang (terverifikasi di kode)

| Hal | Perilaku saat ini | Lokasi |
|---|---|---|
| Atribut sumber tanpa padanan | Pemetaan mengeluarkan NULL (tidak dipaksa). Baik untuk metrik recall atribut baru | `pipeline_runner.py`, `mapping_verifier.py` (`NULL_TARGET`) |
| Katalog atribut | `AttributeCatalog` hidup **di memori**, diisi ulang dari `template_kanonik.xlsx` (59 baris) tiap dibuat; tidak ada penyimpanan | `attribute_policy.py` (`_get_seed_definitions`, `AttributeCatalog()`) |
| Atribut tak dikenal pada rencana dokumen | Dibuat satu `DocumentReviewItem` kategori `NEW_ATTRIBUTE` (status pending). Nilainya **tidak** ditulis ke dokumen | `document_planner.py` ~baris 726 sampai 745 |
| Penyelesaian review `NEW_ATTRIBUTE` | UI hanya menawarkan "Setujui" atau "Tolak". Cabang umum di repositori hanya mengubah status item (approved atau rejected); **tidak mendaftarkan atribut dan tidak menulis nilai** | `streamlit_commit.py` (cabang `elif item.status == "pending"`), `document_repository.py` (cabang `else` di `resolve_review`) |
| Commit | Ditolak selama masih ada review pending | `document_repository.py` baris 305 |
| Penyimpanan atribut dalam dokumen | `KnowledgeDocument.attributes: dict[str, AttributeValue]`, kunci = `attribute_id`. Dokumen hanya memuat atribut yang ada nilainya | `document_contracts.py` |
| Riwayat perubahan | Tabel `kms.document_attribute_changes` (append-only) | `schema_0003_attribute_changes.sql` |

Akibatnya: atribut baru yang disetujui kurator **hilang** setelah review; run berikutnya akan menanyakannya lagi dari nol. Itu bertentangan dengan tujuan "akuisisi pengetahuan adaptif".

## 2. Tujuan fitur

1. Atribut baru yang disetujui kurator terdaftar permanen sebagai atribut kanonik baru (katalog persisten).
2. Nilainya ditulis ke dokumen varietas–lokasi yang relevan.
3. Seluruh dokumen lain mengenali atribut itu: tidak perlu mengisi ulang; atribut hanya muncul pada dokumen yang punya nilai.
4. Run berikutnya yang memuat label sama (atau alias yang disetujui) langsung terpetakan (exact-name atau alias), tanpa review ulang.

## 3. Rancangan

### 3.1 Penyimpanan: katalog persisten (migrasi `0006`)

Tabel `kms.attribute_catalog_ext`, bergaya sama dengan 0003 (append-only, hanya SELECT dan INSERT untuk `cabai_app`):

| Kolom | Isi |
|---|---|
| `attribute_id` (PK), `canonical_key` (unik) | mis. `attr_ph_tanah`, `ph_tanah` |
| `label`, `organ`, `value_type`, `unit`, `description`, `development_stage`, `aliases` (jsonb) | sama dengan `AttributeDefinition` |
| `status` | `approved` atau `deprecated` (tidak ada DELETE; nonaktifkan dengan baris baru) |
| `source_label`, `created_from_run`, `created_by`, `created_at`, `version` | jejak asal dan audit |

Katalog efektif = 59 baris template (tetap) + baris `approved` dari tabel ini. Template Excel tidak diubah.

### 3.2 Alur kurasi untuk `NEW_ATTRIBUTE`

1. **Planner** mengisi payload item: label sumber, contoh nilai, tebakan `value_type` dan `unit` (memakai `parse_cell_value`), tebakan `organ`, daftar dokumen target (`varietas:habitat`) yang punya nilainya, dan kandidat mirip di katalog (untuk mencegah duplikat).
2. **Kurator** memilih salah satu aksi baru:
   - `REGISTER_NEW`: isi atau koreksi label, organ, tipe, satuan. Sistem mendaftarkan atribut ke katalog persisten dan menulis `AttributeValue` (resolution `HUMAN_REVIEW`, dengan `attribute_id` baru) ke dokumen target pada draft.
   - `MAP_TO_EXISTING`: label sumber dijadikan alias atribut yang sudah ada (memakai jalur `/aliases/promote` yang sudah tersedia), nilai ditulis ke atribut itu.
   - `REJECT`: tidak ada yang disimpan; label dicatat sebagai ditolak agar tidak ditanyakan terus (opsional).
3. **Commit** menyimpan dokumen dan katalog dalam satu transaksi; kegagalan salah satu membatalkan keduanya. Perubahan nilai tercatat di `document_attribute_changes`.

### 3.3 Dedup dan penamaan

- Normalisasi label (huruf kecil, spasi, satuan dalam kurung dibuang) dan pencocokan terhadap katalog dan alias sebelum mengizinkan `REGISTER_NEW`.
- `canonical_key` dibuat dari slug label; tabrakan ditolak dan kurator diminta memilih `MAP_TO_EXISTING` atau mengubah label.
- Unik di tingkat database, penyisipan idempoten (aman pada konkurensi).

### 3.4 Integrasi dengan tahap pemetaan (fase 2, opsional)

Supaya run berikutnya memetakan atribut yang baru terdaftar lewat retrieval, baris katalog persisten perlu masuk ke `CanonicalSchema` dan indeks Chroma. Ini **menyentuh bagian yang dievaluasi**, jadi:

- Dilindungi saklar `KMS_DYNAMIC_CATALOG` (bawaan **mati**). Saat mati, perilaku identik dengan yang diuji.
- Saat hidup, `schema_version` dan `template_hash` memuat hash ekstensi, sehingga fingerprint evaluasi berbeda dan hasil tidak tercampur.
- Indeks Chroma ditambah secara inkremental untuk baris baru saja.

Fase 1 (bagian 3.1 sampai 3.3) sudah memenuhi tujuan 1 sampai 3 tanpa menyentuh pemetaan. Tujuan 4 penuh memerlukan fase 2; versi sederhana tujuan 4 dapat dicapai di fase 1 lewat `AttributeCatalog` planner (exact-name pada label dan alias katalog persisten).

## 4. Dampak pada eksperimen yang sudah dilakukan

| Komponen | Terpengaruh? | Alasan |
|---|---|---|
| Mapping F1, recall atribut baru, S1, S2, S4 | Tidak | Keputusan pemetaan tidak berubah (saklar mati, NULL tetap NULL) |
| Klasifikasi foto, fusi | Tidak | Jalur kode berbeda |
| Fingerprint konfigurasi | Tidak berubah saat saklar mati | Dijamin oleh uji regresi di bawah |

**Uji regresi wajib sebelum klaim "hasil lama tetap berlaku":** jalankan harness pada R01 dan S01 (dengan Drive 1) pada commit baru dengan saklar mati; `mapping.csv`, `vision.csv` (status foto), dan `evaluation_config_fingerprint` harus identik dengan hasil yang tersimpan. Satu perbedaan = eksperimen terkait diulang.

Dicatat sebagai deviasi D7 di bagian 12 protokol.

## 5. Evaluasi fitur baru (bukti "akuisisi adaptif")

Eksperimen kecil, terpisah dari metrik inti, memakai pengujian pada commit baru:

| Uji | Cara | Ukuran |
|---|---|---|
| E-A1 Akuisisi | Jalankan N07 (banyak atribut di luar kanonik). Kurator menyetujui atribut yang ditandai gold NO_MATCH | jumlah atribut baru terdaftar, jumlah duplikat yang tertolak, waktu kurasi |
| E-A2 Penggunaan ulang | Jalankan ulang N07 dan jalankan N09 setelah E-A1 | persentase atribut baru yang kini terpetakan otomatis (exact-name atau alias), dan ketepatannya terhadap gold silang dataset |
| E-A3 Keutuhan dokumen | Periksa dokumen setelah commit | atribut baru ada di dokumen target, dokumen lain tidak berubah, riwayat tercatat |

E-A2 memerlukan gold silang dataset (atribut mana di N07 dan N09 yang sama); itu daftar pendek dan dapat disusun dari gold yang ada.

## 6. Risiko dan mitigasi

| Risiko | Mitigasi |
|---|---|
| Katalog tercemar atribut sampah atau duplikat | Persetujuan kurator, pengecekan kemiripan, `deprecated` alih-alih hapus |
| Tabrakan kunci pada konkurensi | Unik di DB, penyisipan idempoten, transaksi tunggal dengan commit dokumen |
| Penyimpangan indeks Chroma dari katalog | Fase 2 memakai saklar dan hash ekstensi; ada perintah bangun-ulang indeks |
| Perubahan memengaruhi hasil evaluasi tanpa disadari | Saklar mati secara bawaan, uji regresi identik, deviasi D7 |
| Tebakan tipe dan satuan salah | Kurator bisa mengoreksi sebelum mendaftar; `value_type` divalidasi oleh `AttributeValue` |

## 7. Tahapan dan perkiraan

| Fase | Isi | Perkiraan |
|---|---|---|
| 1 | Migrasi 0006, katalog persisten, aksi `REGISTER_NEW`/`MAP_TO_EXISTING`/`REJECT` di repositori, API, dan UI; tes unit dan integrasi | 1 sampai 2 hari kerja |
| Regresi | Harness R01 dan S01, pembanding identik, deviasi D7 | setengah hari |
| 2 | Integrasi `CanonicalSchema`/Chroma dengan saklar | 1 sampai 2 hari kerja |
| Evaluasi | E-A1 sampai E-A3, tabel hasil | 1 hari kerja |

## 8. Keputusan yang diperlukan

1. **Siapa yang menyetujui atribut baru:** selalu kurator (disarankan, aman), atau otomatis bila keyakinan tinggi dan tidak ada kandidat mirip?
2. **Cakupan:** fase 1 saja, atau langsung fase 2 (atribut baru ikut dipetakan lewat retrieval pada run berikutnya)?
3. **Atribut ditolak:** diingat agar tidak ditanyakan lagi, atau selalu ditanyakan ulang?
4. **Dua atribut bernama berbeda tetapi bermakna sama:** disatukan lewat alias (disarankan) atau dibiarkan jadi dua kanonik?
5. **Izin mengubah kode produksi** (commit baru di VPS, migrasi DB, restart) dengan pencatatan deviasi D7.

## 9. Catatan implementasi fase 1 (1 November 2026)

- Migrasi `0006` (`schema_0006_attribute_catalog_ext.sql`): tiga tabel append-only (`attribute_catalog_ext`, `attribute_alias_ext`, `attribute_rejections`); `cabai_app` hanya SELECT dan INSERT. Penonaktifan atribut (`deprecated`) **tidak** diimplementasikan di fase 1 karena tabel append-only tanpa UPDATE; ditunda.
- Aksi kurator `REGISTER_NEW`, `MAP_TO_EXISTING`, `REJECT` hanya untuk peran curator, alasan minimal 10 karakter. Keputusan berlaku untuk semua sel dengan label yang sama dalam satu draft. Baris katalog ditulis atomik saat commit, bukan saat review.
- Bila satu dokumen punya beberapa baris dengan nilai berbeda untuk atribut baru, tidak ada nilai yang ditulis (meniru aturan konflik planner); sel itu ditolak dengan catatan.
- Planner menerima `extensions` (katalog persisten) dari API `GET /attributes/catalog`; label yang pernah ditolak tidak ditanyakan lagi.
- Template 60 baris dan tahap pemetaan tidak diubah. Konstruktor `AttributeCatalog()` tetap hanya memuat template (dijaga tes).
- Tes: 9 tes baru (`tests/storage/test_new_attribute_catalog.py`) untuk planner, katalog persisten, aksi kurator, atomisitas, alias, penolakan yang diingat, konflik baris, dan tampilan UI; dua tes UI lama yang memang menegaskan perilaku lama NEW_ATTRIBUTE (dua tombol) dialihkan ke kategori generik `VALUE_INVALID`.
- Catatan: jumlah baris template yang tepat adalah 60 (dokumen lain menyebut 59).

## 10. Batas cakupan penulisan dokumen KMS dan opsi (temuan 1 November 2026)

Fakta (diperiksa dengan `DocumentPlanner.plan_workbook` pada 11 workbook masukan): hanya tata letak "Resume Data" (`data_input.xlsx`: kolom Lokasi Sampling, Jenis Cabai, dua baris header) menghasilkan dokumen varietas-lokasi (9 dokumen, 41 atribut). Sepuluh workbook lain menghasilkan 0 dokumen dengan review LOCATION_UNRESOLVED dan PLANT_IDENTITY_UNRESOLVED. Tahap pemetaan atribut dan keluaran Excel terstandarisasi berjalan untuk semuanya.

| Opsi | Isi | Perkiraan | Catatan |
|---|---|---|---|
| A. Nyatakan sebagai cakupan | KMS V2 menyimpan dokumen dari survei lapangan berformat Resume Data; format lain berakhir di keluaran Excel terstandarisasi. Draf KMS kini melaporkan hal itu (D8) | 0 hari | Jujur dan cukup bila klaim skripsi berpusat pada pemetaan dan standardisasi ke Excel kanonik |
| B. Adaptor dari hasil pipeline | Ubah `canonical_df` dan pemetaan menjadi rekaman planner; varietas dari kolom varietas, habitat `habitat_unknown` bila lokasi tidak ada (jalur `make_unknown_habitat` sudah ada) | 2 sampai 3 hari kerja | Membuat commit KMS berlaku untuk semua format; perlu keputusan tentang identitas varietas tanpa lokasi dan uji pada 9 workbook |
| C. Hanya fase 2 atribut baru | Lanjut ke integrasi atribut baru dengan pemetaan | 1 sampai 2 hari | Tidak mengatasi batas cakupan |

Rekomendasi: A untuk skripsi bila fokus pada pemetaan; B bila klaim "standardisasi data multimodal ke KMS" mencakup penyimpanan akhir untuk data heterogen.

**Keputusan (1 November 2026): opsi A.** Cakupan penulisan dokumen KMS V2 dinyatakan terbatas pada tata letak survei lapangan "Resume Data"; format lain berakhir pada keluaran Excel kanonik terstandarisasi. Rumusan untuk bab batasan masalah dan pembahasan:

> Standardisasi skema dan klasifikasi gambar diuji pada sembilan workbook berbagai struktur dan bahasa. Penulisan akhir ke dokumen varietas-lokasi pada KMS (PostgreSQL JSONB) saat ini mendukung tata letak survei lapangan (kolom lokasi sampling dan jenis cabai); data dengan tata letak lain berhenti pada tabel kanonik terstandarisasi dan tidak ditulis otomatis ke dokumen KMS. Perluasan adaptor untuk tata letak lain menjadi pekerjaan lanjutan.

Panel review dan commit KMS melaporkan batas ini kepada pengguna (D8). Fase 2 atribut baru (atribut menjadi baris kanonik pada tahap pemetaan dan Excel) dikerjakan sebagai skema kanonik dinamis, lihat `docs/RANCANGAN_KANONIK_DINAMIS.md`; katalog atribut fase 1 tetap berlaku pada lapisan dokumen KMS untuk tata letak yang didukung.
