# 03. ADR: private content-addressable image storage

**Status:** accepted for this enhancement; production activation gated by live storage and access tests.

## Context

VPS dilaporkan memiliki 54.9 GB RAM dan sekitar 61 GB NVMe. Angka ini adalah informasi pengguna, bukan hasil inspeksi host. Jenis perangkat NVMe tidak menentukan durability. Dokumentasi Azure membedakan managed disk dengan local temporary/resource disk; yang kedua tidak persisten. Jarvis harus memeriksa mount fisik PostgreSQL dan media sebelum menyimpan bukti riset.

## Decision

Pilih **Opsi C: private R2/S3 authoritative object store**, menggunakan content-addressed keys. Database dan layanan tetap pada VPS. Local CAS (Opsi A) disediakan sebagai backend transisi/dev pada disk persisten yang telah diverifikasi; bukan satu-satunya salinan produksi tanpa backup off-host. Paket menyediakan dua backend alternatif melalui `MEDIA_BACKEND`; ini **bukan implementasi dual-write/cache hybrid otomatis**.

R2 dipilih bila persyaratan lokasi data, fitur API dan pengelolaan akun sesuai. S3 merupakan alternatif ketika kontrol IAM/retention/region yang dibutuhkan lebih sesuai di AWS. Biaya aktual, pajak, egress antar-cloud dan region harus dihitung dari tarif saat deployment; tidak ada klaim R2 pasti termurah untuk semua workload.

| Kriteria | A: Local CAS + Caddy | B: Single-host MinIO | C: Private R2/S3 |
|---|---|---|---|
| Operasional awal | Paling sederhana | Menambah service, upgrade, credentials, disk management | Menambah akun, jaringan dan kebijakan bucket |
| Batas disk VPS | Tetap dibatasi disk lokal | Tetap dibatasi disk yang sama | Growth media tidak menghabiskan root volume |
| Failure domain | Sama dengan VM | Tetap VM yang sama; container tidak membuat HA | Terpisah dari kehilangan VM, tetapi bukan kebal kompromi akun |
| Akses | Harus ada auth di depan media; hash bukan secret | Bucket privat/policy dan reverse proxy | Bucket privat + aplikasi berautentikasi |
| Latency | Terendah pada host | Rendah lokal | Memerlukan jaringan; ukur p95 dan timeout |
| Konsistensi/immutability | Atomic publish + fsync dalam kode | Tergantung S3 feature/version dan disk | Conditional put; validate compatibility terhadap provider yang dipilih |
| Keputusan | Transisi/dev atau offline-first terkontrol | Tidak dipilih untuk satu VM kecil | Rekomendasi produksi pada batasan saat ini |

## Capacity reasoning

Contoh anggaran, **bukan hasil pengukuran**: 10.000 foto x 3 MB original = 30 GB. Bila derivative rata-rata 0.5 MB dan thumbnail 0.02 MB, total sekitar 35.2 GB sebelum source XLSX, output, database, WAL, embeddings, logs, backup sementara dan filesystem reserve. Original tidak boleh dihapus hanya karena WebP sudah dibuat. RAM besar tidak menyelesaikan storage capacity/durability ini.

Local backend menolak write bila cadangan default 5 GiB akan terlanggar. Cadangan ini batas pengaman awal, bukan capacity plan. Jangan membersihkan disk dengan menghapus original atau WAL secara manual. Hentikan ingestion, pulihkan kapasitas/archiving, lalu replay dari sumber terarsip.

## ImageStorageManager

Modul `src/storage/image_storage.py` menyediakan `from_bytes`, `from_stream`, dan `from_drive`. Drive menggunakan authorized streaming request ke endpoint Google yang tetap; tidak menerima URL arbitrary, tidak mengikuti redirect, memiliki batas byte dan deadline. Service account hanya membutuhkan scope Drive read-only dan akses folder yang diizinkan.

Input didekode dengan Pillow sebagai JPEG/PNG/WebP, bukan dipercaya dari extension/MIME. Image kosong, korup, animasi/multipage dan decompression-budget violation ditolak. Default batas 25 MiB dan 40 juta pixel; concurrent decoding dibatasi dua per manager untuk mengurangi lonjakan memori.

Original disimpan utuh sebagai bukti privat. Derivative diorientasikan dengan EXIF, kemudian metadata EXIF/GPS/ICC/XMP/comment dihapus. Gambar utama dibatasi sisi maksimum 2560 px; WebP quality 80. Thumbnail 256x256 dipadding agar organ tidak terpotong, bukan center crop. SHA-256 dihitung **terpisah** untuk original, WebP utama dan thumbnail. Transform profile mencakup format/prosedur, dimensi, versi Pillow dan libwebp.

WebP quality 80 bersifat lossy. Jangan menggunakan derivative sebagai bukti kuantitatif tunggal untuk analisis warna/ukuran ilmiah. Original tetap tersedia secara privat untuk analisis yang tepat. Hook vision mengirim derivative yang sudah dibersihkan dan mencatat inference SHA; perubahan input ini wajib divalidasi terhadap baseline vision sebelum aktif. Tidak ada klaim bahwa kualitas klasifikasi tidak berubah.

Contoh penggunaan di aplikasi Python:

```python
from pathlib import Path
from src.storage.image_storage import ImageStorageManager, LocalCAS

store = LocalCAS(Path('/srv/media/cabai-kms'), min_free_bytes=5 * 1024**3)
manager = ImageStorageManager(store)
with Path('/srv/imports/foto_buah.jpg').open('rb') as stream:
    asset = manager.from_stream(stream)
metadata_for_postgres = asset.as_dict()
```

Path contoh harus merupakan file nyata milik deployment; library tidak melakukan crawling tambahan atau menebak nama file.

## Keys dan URI

```text
sources/ab/cd/<sha256>.xlsx
originals/ab/cd/<original_sha256>.bin
images/ab/cd/<webp_sha256>.webp
thumbs/ab/cd/<thumbnail_sha256>.webp
```

Backend lokal mengembalikan `cas:///...`; cloud mengembalikan `s3://bucket/...`. URI itu identitas storage internal, bukan public URL. `/media/{asset_id}/image` dan `/media/{asset_id}/thumbnail` melayani bytes setelah autentikasi. API tidak menyediakan endpoint original publik. `MEDIA_PUBLIC_BASE_URL` dipertahankan sebagai konfigurasi base URL akses media berautentikasi; namanya tidak berarti bucket menjadi public. Pada paket awal, Streamlit mengambil bytes melalui `KMS_API_BASE_URL`, bukan mengandalkan URL bucket.

SHA collision secara operasional amat berbeda dari nama file sama: deduplikasi tidak memakai nama file. Asset yang identik dapat memiliki beberapa plant-image links ke run/organ; situasi ini tetap harus masuk audit, bukan dipakai untuk menyimpulkan dua tanaman sama.

## Durability dan konsistensi DB/object store

Local CAS memakai validasi key, penolakan symlink/traversal, lock ruang disk, tempfile di filesystem yang sama, fsync, dan atomic no-clobber publication dengan hard link. S3 backend melakukan conditional PUT `If-None-Match: *`; duplicate memverifikasi checksum metadata dan ukuran. Pembacaan menghitung ulang SHA dari bytes. Endpoint S3-compatible yang tidak memenuhi semantik ini tidak boleh dianggap kompatibel hanya karena namanya S3.

Urutan operasi: persist original -> persist derivative -> persist thumbnail -> register asset -> commit plant relation. Object storage dan PostgreSQL tidak berbagi transaksi atomik. Kegagalan di tengah bisa meninggalkan objek orphan yang aman untuk diinventarisasi; **jangan menghapus otomatis** berdasarkan umur pendek, sebab run/review mungkin belum dipublikasikan. Collector mendatang perlu mark-and-sweep, grace period lebih panjang dari retention draft/checkpoint, manifest referensi lengkap dan dry-run curator.

Pemindahan backend bukan sekadar mengganti environment variable: registry masih menunjuk URI lama. Salin dan verifikasi semua objek terlebih dahulu, siapkan resolver dual-backend atau migrasi URI yang diaudit, lalu cutover. Immutable asset records tidak boleh diupdate langsung oleh app untuk menyembunyikan perpindahan. Paket ini tidak mengotomasi migrasi backend.

## Security: apa yang dilindungi dan yang tidak

Bucket tetap private; jangan mengaktifkan r2.dev/public custom domain. Credentials dibatasi bucket/kebutuhan operasi dan disimpan di environment file privat. S3/R2 retrieval dilakukan server-side; token tidak berada di URL, JSON response, Excel, atau log akses. Contoh Caddy hanya mem-proxy Streamlit di belakang auth, **tanpa `file_server /srv/media`**. Untuk media volume lebih besar, pertimbangkan auth_request/forward_auth dan private file serving, tetapi harus diuji agar tidak ada route bypass.

Bearer token bersama mengidentifikasi layanan, bukan manusia tertentu. Reader paket ini dapat membaca seluruh workspace; bukan ACL per varietas atau tenant. OIDC, assignment reviewer, tenant scoping dan RLS adalah langkah sebelum external SaaS.

Zero leak absolut tidak dapat dijanjikan. Root, admin bucket, credential theft, screenshot pengguna sah, dan isi foto yang sudah memuat tulisan sensitif tetap dapat mengekspos data. Metadata stripping tidak menghapus teks yang terlihat di foto. Original masih mengandung metadata dan harus diakses hanya untuk tujuan penelitian yang sah. Pengiriman ke 9Router/provider merupakan jalur egress terpisah: telaah retention/logging provider, whitelist outbound destinations, mask field sensitif bila diperlukan, dan jangan menganggap private bucket berarti LLM egress juga private.

## Live acceptance tests

Wajib: anonymous media request ditolak; reader bisa membaca derivative yang benar; MIME WebP dan no-store; original tidak memiliki route publik; input corrupt/oversize gagal; checksum roundtrip sumber/original/derivative sesuai; upload duplikat tidak membuat asset berbeda; objek di bucket tidak dapat dibaca tanpa credentials; restart VM tidak menghilangkan data authoritative; simulated store failure tidak menghasilkan receipt commit sukses; restore database dapat membaca kembali semua referensi media yang dipakai.

S3 unit tests memakai botocore Stubber dan **tidak membuktikan** IAM, bucket privacy, conditional PUT live, availability, atau billing. Pengujian pada akun/bucket nyata tetap wajib.
