# URUTAN PENERAPAN UNTUK JARVIS / VPS-BOSS

## Otoritas, batas perubahan, dan prinsip penghentian

Tugas Anda adalah **mengintegrasikan enhancement ke sistem yang sudah ada**, bukan membangun ulang CABAI-KMS, mengganti crawler, mengubah hierarchy agent, atau mengganti provider 9Router. Periksa kode dan konfigurasi VPS sebagai sumber kebenaran. Paket adalah release candidate yang harus disesuaikan dengan kontrak aktual dan dibuktikan melalui tests.

Jangan menjalankan `git reset --hard`, menghapus database, memformat disk, memindahkan root volume, menimpa `.env`, mengubah gateway global, atau me-restart seluruh office AI. Jangan mengatasi error migrasi dengan DROP schema produksi. Bila identitas repo, anchor patch, data model, dependency pins, role, storage, atau tests tidak cocok: **hentikan aktivasi**, simpan laporan ketidakcocokan, buat patch adaptasi kecil pada branch, lalu ulang pengujian. Tidak ada izin untuk mengarang sukses test atau mengubah assertion agar test menjadi hijau.

Path `/srv/cabai-kms`, user `cabai`, port 8091 dan port UI 8501 adalah default paket, bukan hasil inspeksi host. Gunakan konfigurasi service yang benar-benar ditemukan; adaptasikan path/user/port unit bila berbeda. Jangan menjalankan kedua UI pada port yang sama.

## 0. Inventarisasi non-destruktif

```bash
hostnamectl
free -h
df -hT
lsblk -o NAME,SIZE,TYPE,FSTYPE,MOUNTPOINTS,MODEL
findmnt -T /srv
findmnt -T /var/lib/postgresql
systemctl list-units --type=service --all | grep -Ei 'cabai|streamlit|caddy|postgres|jarvis'
ss -lntp
python3 --version
```

Jika PostgreSQL belum ada, `findmnt -T /var/lib/postgresql` bisa gagal; itu bukan izin membuat atau memformat disk. Cocokkan mount dengan Azure managed disks/IMDS/portal. **PostgreSQL dan authoritative local media dilarang berada pada temporary/resource disk.** Verifikasi jumlah vCPU dan beban agent lain sebelum memilih concurrency. Simpan inventaris tanpa credentials atau isi `.env`.

Cari checkout melalui `WorkingDirectory`/`ExecStart` service yang aktif. Set variabel setelah lokasi nyata diketahui:

```bash
export REPO=/srv/cabai-kms
export ZIP=/tmp/CABAI_KMS_Enhancement_v1.0.0-rc1.zip
test -d "$REPO/.git"
cd "$REPO"
git remote -v
git status --short
git rev-parse HEAD
```

Pastikan remote adalah repo yang diminta dan branch/commit relevan. Jangan menyalin token remote ke laporan. Pemeriksaan ini juga harus membandingkan signature `PipelineRunResult`, `run_pipeline_ui`, `ReviewItem`, `apply_review_corrections`, domain/keys canonical, dan node vision dengan adapter paket. Kode publik yang diaudit tidak menjamin checkout VPS identik.

## 1. Branch dan ekstraksi

Simpan/commit perubahan lokal yang memang diotorisasi terlebih dahulu; jangan stash/delete otomatis. Perintah berikut sengaja menolak working tree kotor.

```bash
cd "$REPO"
test -z "$(git status --porcelain)" || { echo 'STOP: working tree tidak bersih'; exit 1; }
git switch -c enhancement/kms-persistence-v1
export BASE_COMMIT="$(git rev-parse HEAD)"
export EXTRACT_DIR="$(mktemp -d /tmp/cabai-enhancement.XXXXXX)"
unzip -q "$ZIP" -d "$EXTRACT_DIR"
export PKG="$EXTRACT_DIR/CABAI_KMS_Enhancement"
test -f "$PKG/schema.sql"
```

Cocokkan checksum ZIP dengan `.sha256` yang disertakan sebelum ekstraksi. Bila branch sudah ada, berhenti dan inspeksi; jangan memakai `git switch -C` untuk menimpa branch. Baca `README.md`, `IMPLEMENTATION_STATUS.md` dan hasil pengujian paket.

## 2. Installer: inspect, patch, diff

```bash
python3 "$PKG/scripts/install_into_repo.py" --repo "$REPO"
python3 "$PKG/scripts/install_into_repo.py" --repo "$REPO" --apply
cd "$REPO"
git diff --stat
git diff -- src/ui/app.py src/ui/pages/3_Hasil.py src/orchestrator/graph.py requirements.txt
python3 -m compileall -q src/storage src/integrations src/kms_api
```

Tanpa `--apply`, installer hanya merencanakan dan memvalidasi AST/anchor. Dengan `--apply`, ia menyalin namespace enhancement, DDL/deploy/tests/scripts, mencatat backup dan SHA sebelum/sesudah di `.kms_backups/`, lalu menerapkan tiga hook dan menambahkan halaman `4_KMS.py`. Dokumentasi masuk `docs/kms/`; README repo asli tidak ditimpa. `config/characteristics_overrides.json` existing dipertahankan.

Jika anchor gagal, jangan pakai regex luas untuk memaksakan patch. Adaptasikan integrasi berdasarkan fungsi yang sebenarnya. Pertahankan kontrak run ID, hash sumber, schema version, corrected replay dan provider trace. Pastikan panel commit membaca **result original untuk provenance dan result corrected untuk nilai**, bukan sekadar `st.data_editor` tanpa identitas.

## 3. Python environment tanpa merusak deployment lama

Gunakan Python 3.11+ yang didukung dependencies; local test paket dijalankan pada Python 3.13. Simpan venv/lock produksi lama untuk rollback. Tinjau ruang disk karena dependencies embedding dapat besar.

```bash
cd "$REPO"
python3 -m venv .venv-kms
.venv-kms/bin/python -m pip install --upgrade pip
.venv-kms/bin/python -m pip install -r requirements.txt
.venv-kms/bin/python -m pip install -r "$PKG/requirements-test.txt"
.venv-kms/bin/python -m pip check
```

Installer menambahkan `-r requirements-kms.txt` sekali ke requirements existing. Jika pins berbenturan dengan dependencies repo, jangan `--no-deps`/force downgrade sembarang: buat resolusi kompatibel, simpan perubahan, ulang seluruh test. API dapat dijalankan pada venv terpisah yang hanya menginstal requirements-kms; UI tetap membutuhkan dependencies integrasi. Jangan beranggapan paket KMS sudah menginstal Streamlit/LangGraph/embedding milik repo.

Buat transitive lock sesuai platform setelah resolver berhasil, misalnya dengan `pip-tools` pada environment build terisolasi:

```bash
.venv-kms/bin/python -m pip freeze > "$EXTRACT_DIR/resolved-environment.txt"
.venv-kms/bin/python -m pip check
```

`freeze` adalah inventaris, bukan hash-locked supply-chain guarantee. Sebelum produksi, gunakan mekanisme lock/hash yang berlaku di repo dan lakukan dependency vulnerability review. Direct pins paket tidak disamakan dengan seluruh dependencies transitif yang sudah diaudit.

## 4. Instal PostgreSQL dan identitas baru

Pada Ubuntu yang repository-nya menyediakan PostgreSQL >=15:

```bash
sudo apt-get update
sudo apt-get install -y postgresql postgresql-contrib python3-venv
sudo systemctl enable --now postgresql
sudo -u postgres psql -X -A -t -c 'SHOW server_version_num;'
```

Bila versi di bawah 15, berhenti dan rencanakan instalasi versi yang didukung melalui sumber resmi; jangan upgrade cluster produksi lain tanpa rencana. PostgreSQL existing milik aplikasi lain tidak boleh di-reset.

Untuk deployment baru dengan user service `cabai`:

```bash
id cabai || sudo useradd --system --create-home --home-dir /var/lib/cabai --shell /usr/sbin/nologin cabai
sudo install -d -o cabai -g cabai -m 0750 /srv/media/cabai-kms
sudo python3 "$REPO/scripts/kms/bootstrap_postgres.py" --runtime-user cabai --output-dir /etc/cabai-kms
```

Bootstrap membuat `cabai_migrator`, `cabai_app`, database `cabai_kms`, dan tiga file secret private: `runtime.env`, `ui.env`, `migration.env`. Script **menolak identitas/file existing** agar tidak mengubah password atau ownership diam-diam. Jika database sudah ada, reconcile grants/ownership/secret secara eksplisit menggunakan administrator dan skip bootstrap; jangan drop untuk mempermudah.

`migration.env` mode 0600 root-only; runtime/UI env dimiliki account layanan. Password/token digenerasikan, tidak dicetak ke terminal. Jika bootstrap terputus, file tersebut adalah recovery material; cek keadaan role/database lalu lanjut secara terkendali. Jangan menghapusnya lalu mengulang sambil meninggalkan role tanpa password yang diketahui.

Periksa `SHOW listen_addresses` dan `pg_hba.conf`: bind PG ke loopback/private interface yang disepakati, gunakan SCRAM untuk koneksi TCP, dan jangan membuka 5432 ke Internet. Tidak ada perubahan firewall/pg_hba global otomatis dari paket.

## 5. Eksekusi migration dan grants

```bash
cd "$REPO"
sudo "$REPO/.venv-kms/bin/python" "$REPO/scripts/kms/apply_release.py" \
  --env-file /etc/cabai-kms/migration.env --grants "$REPO/deploy/grants.sql"
sudo -u postgres psql -X -d cabai_kms -c 'TABLE kms.schema_migrations;'
```

Runner menjalankan DDL di transaksi dan advisory lock, menyimpan checksum, lalu grants least privilege. Jalankan lagi untuk memverifikasi idempotency migrasi; hasil `applied` kedua harus kosong. Jika checksum berbeda, buat migration baru dan registration baru pada `MIGRATIONS`; **jangan edit ledger atau schema.sql yang sudah deployed**.

Untuk pengembangan cepat, `python -m src.storage.migrate` juga tersedia ketika `DATABASE_ADMIN_URL` disuntikkan secara aman ke environment proses. Produksi memakai release command di atas, bukan membawa admin URL ke API. Default `DB_AUTO_MIGRATE=false` tetap dipertahankan.

## 6. Konfigurasi environment dan storage

Jangan mengganti `.env` lama. File `.env.kms.example` hanya referensi nama setting. EnvironmentFile systemd lebih sesuai untuk secrets produksi; bila harus merge `.env`, tambahkan hanya key yang diperlukan, mode 0600, dan pastikan diabaikan Git. Pertahankan semua `CABAI_KMS_*PROVIDER`, endpoint 9Router dan model aliases existing.

Untuk smoke test lokal di managed disk, backend local dapat dipakai. Sebelum produksi pilih R2/S3 private, lalu isi pada `/etc/cabai-kms/runtime.env` menggunakan editor/secret manager yang tidak membocorkan nilai:

```text
MEDIA_BACKEND=s3
S3_ENDPOINT_URL=https://<account-yang-diverifikasi>.r2.cloudflarestorage.com
S3_BUCKET=<bucket-private-yang-diverifikasi>
S3_REGION=auto
S3_ACCESS_KEY_ID=<secret>
S3_SECRET_ACCESS_KEY=<secret>
GOOGLE_DRIVE_CREDENTIALS_PATH=/etc/cabai-kms/drive-reader.json
```

Teks angle-bracket adalah **nilai konfigurasi operator**, bukan perintah siap dieksekusi. Jangan mengarang account/bucket/credential. Bucket harus non-public, credentials scoped, Drive JSON mode 0600 readable hanya oleh API user. Validasi provider-specific conditional PUT dan private GET. Untuk AWS S3, pakai region yang benar dan endpoint standar/yang disetujui; jangan memakai `auto` tanpa memeriksa kompatibilitas provider.

Pilih backend authoritative **sebelum run produksi pertama**. Beralih dari local ke S3 setelah data terdaftar memerlukan migrasi URI/object yang diaudit; mengganti env saja akan membuat referensi lama tidak bisa dibaca backend baru.

`KMS_PROVIDER_MANIFEST_JSON` pada environment UI harus merekam requested model alias, actual provider/model yang sudah diverifikasi, endpoint identifier tanpa secret, prompt/config release hash dan verifier/normalizer version. `{}` diperbolehkan untuk transisi tetapi tercatat sebagai manifest tidak lengkap. Alias `ag/...` dari 9Router tidak boleh dianggap otomatis sama dengan nama model API resmi; verifikasi lewat gateway dan provider trace aktual, tanpa mengubah model yang sudah berjalan.

Curate `characteristics_overrides.json` berdasarkan canonical_key existing dan unit yang benar. Jangan menyalin daftar karakter buatan atau menentukan semua ukuran memakai cm. Perubahan semantic unit/type perlu versi katalog/migrasi, bukan patch kosmetik.

## 7. Unit test dan real PostgreSQL integration test

Dari paket ekstraksi, memakai venv yang sudah terpasang:

```bash
cd "$PKG"
"$REPO/.venv-kms/bin/python" -m pytest -q -m 'not integration'
```

Untuk database uji disposable dengan Docker yang **sudah tersedia dan diotorisasi**:

```bash
cd "$PKG"
docker compose -f deploy/compose.test.yml up -d --wait
export TEST_DATABASE_URL='postgresql+psycopg://cabai_test:local_disposable_test_only@127.0.0.1:54329/cabai_kms_test'
export TEST_DATABASE_ADMIN_URL="$TEST_DATABASE_URL"
"$REPO/.venv-kms/bin/python" -m pytest -q -m integration
unset TEST_DATABASE_URL TEST_DATABASE_ADMIN_URL
docker compose -f deploy/compose.test.yml down
```

Password tersebut hanya fixture database tmpfs lokal. Jangan gunakan di cabai_kms produksi. Tests menolak nama database yang tidak berakhir `_test`. Docker fixture menggunakan owner role untuk menguji fungsi DDL/transactions; **bukan** bukti least-privilege runtime, sehingga langkah role check/live API berikut tetap wajib. Bila Docker tidak tersedia, administrator menyediakan database disposable `_test` dan env credentials yang sesuai; jangan memasang/mengubah Docker daemon global tanpa persetujuan.

Semua integration tests harus benar-benar dieksekusi; `SKIPPED` tidak memenuhi gate. Tests mencakup commit replay, dua commit paralel, stale revision, pending review, rollback konflik, protection human values, immutable evidence, alias scoping, dan penolakan source-less run.

Regression repo:

```bash
cd "$REPO"
.venv-kms/bin/python -m pytest -q
```

Jika suite repo memiliki network/provider tests, pisahkan menurut marker existing dan catat yang belum dieksekusi. Jangan menjalankan test yang mengubah production state tanpa sandbox. Tambahkan satu real sample row-oriented dan satu transposed/header bertingkat dari repo; bandingkan canonical output/provenance sebelum dan sesudah dengan `KMS_ENABLED=false`, lalu true. Buktikan normalizer/mapping baseline tidak berubah oleh storage hook. Vision dapat berubah karena input derivative; ukur dan laporkan, jangan menutupinya.

## 8. Jalankan API terisolasi

Baca unit `deploy/cabai-kms-api.service`. Sesuaikan hanya path/user/port yang berbeda dari inventaris. Pastikan account API bisa membaca kode/venv dan menulis media path; jangan `chown -R` seluruh VPS. API hanya bind loopback 8091; satu worker dan decode/concurrency limit konservatif.

```bash
sudo install -m 0644 "$REPO/deploy/cabai-kms-api.service" /etc/systemd/system/cabai-kms-api.service
sudo systemctl daemon-reload
sudo systemctl enable --now cabai-kms-api
sudo systemctl status cabai-kms-api --no-pager
curl --fail --silent http://127.0.0.1:8091/healthz
```

Healthz hanya liveness. Readyz terautentikasi memeriksa database; API startup menolak app URL yang superuser/schema owner. Untuk source dan foto nyata gunakan script berikut; tidak ada nilai varietas palsu yang dimasukkan oleh script ini:

```bash
cd "$REPO"
sudo -u cabai "$REPO/.venv-kms/bin/python" "$REPO/scripts/kms/verify_service.py" \
  --env-file /etc/cabai-kms/ui.env --source /srv/imports/contoh_lapangan.xlsx \
  --image /srv/imports/foto_buah.jpg
```

Ganti dua file contoh dengan fixture nyata yang diizinkan. Hasil wajib menunjukkan source roundtrip dan image dedup/thumbnail sukses. Request tanpa bearer ke `/values`/media harus 401. Pastikan akses object melalui public endpoint bucket gagal. Jangan menyimpan output command yang mengandung tokens/DSN; script sengaja hanya mencetak status.

## 9. Aktifkan integrasi Streamlit secara terkendali

Tambahkan EnvironmentFile `/etc/cabai-kms/ui.env` ke **unit Streamlit existing**, mengikuti snippet `deploy/cabai-kms-ui.env.conf`. Pindahkan ExecStart UI ke candidate venv hanya setelah regression lulus; simpan ExecStart lama untuk rollback. Pastikan token reviewer server tersedia untuk initial pipeline capture; per-user token pada halaman Hasil saja tidak menggantikan konfigurasi initial-run service token.

Ubah `KMS_ENABLED=true` pada environment UI setelah tests dan live smoke test lulus. Backend API tidak memakai flag ini untuk routing; flag mengendalikan hook lama/baru pada UI/graph. Restart hanya service Streamlit terkait, bukan gateway/office seluruh agent. `KMS_ENABLED=false` mengembalikan jalur ingestion lama tetapi tidak menghapus database.

Lakukan live run pada source nyata: sumber harus sudah terarsip sebelum model berjalan, initial draft muncul, pending review menghalangi commit, setiap koreksi tersimpan di pusat, lalu tombol **Commit & Sinkronkan ke PostgreSQL KMS** menghasilkan receipt. Tombol ulang tidak menambah observations/outbox. Periksa `4_KMS.py` dan cocokkan nilai/status/unit/provenance. Lakukan reload browser, tutup sesi, kemudian recover lewat run ID tanpa memanggil model lagi.

Crash/recovery gate: simulasikan worker/API stop setelah stage dan setelah commit acknowledgment timeout di lingkungan uji. Retry harus menghasilkan receipt existing, bukan penulisan ganda. Untuk review, putuskan API: UI tidak boleh mengklaim keputusan tersimpan. Pulihkan API dan review dari draft pusat. Current HUMAN_REVIEW tidak boleh tertimpa AUTO_ACCEPT run berikutnya.

## 10. Caddy dan pembatasan akses

Default paket tidak mempublikasikan API atau folder media. Streamlit memanggil API melalui loopback dan menyajikan data setelah autentikasi gateway existing. Jika perlu situs baru, **merge**, bukan overwrite, `deploy/Caddyfile.kms` ke konfigurasi Caddy setelah host/user/hash password yang benar tersedia. Jangan mengubah situs atau port agent lain.

```bash
sudo caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
```

Jalankan reload hanya setelah validasi konfigurasi final dan environment variables yang dibutuhkan lulus. Konfigurasi Caddy existing yang sudah aman tidak harus diubah. Dilarang menambahkan `file_server` publik untuk `/srv/media/cabai-kms`, menaruh token di query string, atau membuka port PostgreSQL/8091 ke Internet untuk memudahkan debugging.

## 11. Backup, restore dan gate produksi

Sebelum go-live tentukan RPO/RTO, persistent managed disk DB, backup off-host, WAL archiving/PITR, retention dan restore drill. `pg_dump` berguna untuk logical export, tetapi bukan pengganti base backup/WAL untuk PITR. Penyimpanan database dan backup di disk VM yang sama tidak memenuhi disaster recovery.

Paket tidak menginstal topologi replikasi, pgBackRest, bucket retention atau managed PostgreSQL otomatis. Implementasikan sesuai sistem backup VPS existing dan dokumentasi resmi; jangan menyalin archive_command yang menimpa file. Uji restore pada instance terpisah, cek jumlah run/observations/audit dan checksum media. Jangan menyatakan zero loss hanya karena `synchronous_commit=on`.

Dokumentasikan: baseline commit SHA, package SHA, exact dependency lock, hasil semua test, storage type/mount yang diverifikasi, actual provider manifest, migration ledger, role matrix, anonymized screenshot receipt, restore result, serta risiko yang belum terselesaikan. **Belum ada hasil live ini dalam paket; Jarvis harus menghasilkan bukti aktual.**

## 12. Rollback yang tidak menghapus pengetahuan

Bila UI bermasalah, set `KMS_ENABLED=false`, kembalikan ExecStart/venv UI lama yang disimpan, restart service itu saja. Biarkan PostgreSQL, media dan review evidence tetap utuh. Jangan down-migrate atau drop schema untuk rollback aplikasi. Pulihkan patch dari branch/backup manifest setelah memastikan tidak ada perubahan pengguna yang ditimpa. Jangan menggunakan `git reset --hard` sebagai prosedur otomatis.

Setelah perbaikan, create release/migration baru bila schema berubah. Committed run tetap immutable; correction membuat amendment run, bukan menulis ulang masa lalu.
