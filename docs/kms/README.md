# CABAI-KMS: persistence, evidence, review, and private media

**Enhancement package v1.0.0-rc1 | 29 September 2026**

Paket ini memperluas **AgenticAI_CabaiKMS**, bukan mengganti crawler, normalizer, gateway 9Router, atau LangGraph yang sudah berjalan. Tujuannya mengubah hasil akuisisi sementara menjadi pengetahuan yang dapat ditelusuri, direview, disimpan, dan dipulihkan.

## Keputusan utama

PostgreSQL menjadi sumber kebenaran KMS. Nilai kanonik terkini dipisahkan dari observasi dan keputusan manusia yang tidak ditimpa. Foto asli disimpan sebagai bukti; WebP dan thumbnail merupakan turunan. FastAPI memisahkan layanan persistence dari Streamlit. R2/S3 privat direkomendasikan sebagai penyimpanan media produksi; local CAS tersedia untuk transisi di disk persisten yang telah diverifikasi.

Implementasi ini adalah **modular monolith dengan service boundary**, bukan microservices yang memerlukan Kubernetes/Kafka. Driver yang dipakai adalah SQLAlchemy 2 + psycopg 3 sinkron. Endpoint sinkron dijalankan FastAPI di thread pool; operasi blocking pada endpoint async dipindahkan dengan `asyncio.to_thread`. Pemilihan ini disengaja untuk transaksi review/commit yang relatif singkat.

## Isi paket

| Lokasi | Fungsi |
|---|---|
| `schema.sql` | DDL PostgreSQL, constraint, indeks, view 3NF, audit dan append-only triggers |
| `src/storage/` | Kontrak, ORM, repository, migrasi, learning, CAS lokal/S3, outbox |
| `src/kms_api/app.py` | API dengan autentikasi bearer dan peran reader/reviewer/curator |
| `src/integrations/` | Adapter hasil pipeline, arsip sumber, review persistence, hook vision, panel Streamlit |
| `scripts/install_into_repo.py` | Installer dengan pemeriksaan anchor, AST, backup, dan manifest perubahan |
| `scripts/bootstrap_postgres.py` | Pembuatan database/role baru dan kredensial privat tanpa mencetak secret |
| `scripts/apply_release.py` | Migrasi satu kali per deployment, lalu pemberian hak runtime |
| `scripts/verify_service.py` | Live archive/media smoke test tanpa membuat nilai riset sintetis |
| `deploy/` | Grants SQL, systemd, Caddy snippet, PostgreSQL disposable untuk integration test |
| `tests/` | Unit/contract/API/image tests dan integration test PostgreSQL sungguhan |
| `docs/` | Audit, spesifikasi, ADR media, panduan Jarvis, status implementasi dan sumber |

## Status verifikasi

Lihat `docs/VALIDATION_REPORT.md` untuk hasil akhir yang benar-benar dieksekusi. Lingkungan penyusunan memiliki library Python untuk unit test, tetapi **tidak memiliki PostgreSQL aktif, psycopg, Streamlit, kredensial Drive/R2, atau akses VPS pengguna**. Karena itu, lulusnya unit test bukan bukti lulusnya transaksi SQL, integrasi seluruh repo, atau deployment produksi. Integration test yang tidak memiliki server akan ditandai **SKIPPED**, bukan disamarkan sebagai lulus.

Audit sumber dilakukan terhadap file publik yang berhasil dibaca melalui GitHub/raw; bukan clone lengkap pada satu commit yang terjamin konsisten. Installer mencatat `git rev-parse HEAD` pada VPS dan berhenti ketika titik integrasi tidak cocok. Jalankan regression test repo pada commit tersebut sebelum mengaktifkan fitur.

## Jalur penerapan

Baca `docs/URUTAN_PENERAPAN_AGENT_VPS.md`. Jangan menyalin seluruh isi ZIP dengan overwrite ke repo aktif. Ekstrak ke direktori terpisah, jalankan installer tanpa `--apply` untuk pemeriksaan, kemudian tinjau rencana dan diff. `KMS_ENABLED=false` mempertahankan jalur lama sampai seluruh gerbang pengujian lulus.

```bash
python scripts/install_into_repo.py --repo /srv/cabai-kms
python scripts/install_into_repo.py --repo /srv/cabai-kms --apply
```

Perintah menggunakan `/srv/cabai-kms` sebagai contoh lokasi deployment yang konsisten dengan unit systemd. Jarvis wajib menyesuaikan path dengan checkout sebenarnya, **tanpa memindahkan atau menimpa deployment yang berjalan**.

## Semantik jaminan

Commit atomik mencakup current values, observasi, keputusan review, gold examples, referensi foto, receipt, dan transactional outbox. Pengulangan commit dengan run/revisi/digest yang sama mengembalikan receipt lama. File disimpan terlebih dahulu; kegagalan transaksi bisa meninggalkan objek tak terpakai, bukan referensi baru ke objek yang belum pernah berhasil ditulis.

Ini bukan jaminan absolut zero data loss atau zero leak. PostgreSQL tunggal tetap memiliki risiko kehilangan host, disk, atau kredensial. Dibutuhkan disk persisten, backup off-host, WAL/PITR, pembatasan akses, dan restore drill. RPO mendekati nol atau nol untuk commit yang diakui membutuhkan desain replikasi dan failover tambahan sesuai failure model.

## Batas cakupan yang penting

Worker ingestion async multi-file, migrasi checkpointer LangGraph ke PostgreSQL, penggantian Chroma dengan pgvector, OIDC/multi-tenancy, dan frontend Next.js **belum diaktifkan oleh paket ini**. Semuanya memiliki rancangan dan kriteria promosi dalam roadmap. Outbox yang tersedia adalah worker notifikasi pasca-commit, bukan antrean eksekusi ingestion.

Gold corrections disimpan otomatis saat commit. Alias membutuhkan promosi curator dan referensi evaluasi; resolver disediakan, tetapi installer **tidak menyisipkan alias baru ke matcher lama secara diam-diam**. Aktivasi lookup dalam matching adalah perubahan perilaku yang harus melalui shadow evaluation.
