# Checkpoint Log

Running record of blueprint checkpoints and their verification evidence.
Each entry is a snapshot at the time it was verified — re-run the
referenced command if you need current state, don't assume this stays
accurate as the underlying Drive folder / templates / samples change.

## Fase 4 — Drive Crawler

**Checkpoint:** "Kamu buat service account & share folder citra sampel;
verifikasi crawler mengembalikan metadata nyata."

**Status:** ✅ Verified 2026-07-20.

**Setup confirmed:**
- Service account: `drive-reader-bot@tugasakhir-503001.iam.gserviceaccount.com`
  (GCP project `tugasakhir-503001`), key at `credentials.json` (gitignored).
- `.env`: `GOOGLE_DRIVE_CREDENTIALS_PATH=credentials.json`,
  `GOOGLE_DRIVE_FOLDER_ID=1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g`.
- Folder shared with the service account (Viewer) — see `docs/DRIVE_SETUP.md`.

**Command:**
```bash
python -c "
from src.agents.drive_crawler import list_images
imgs = list_images()
print(len(imgs), 'images found')
for i in imgs:
    print('-', i.filename, '|', i.mime_type, '|', i.size, 'bytes |', i.created_time)
"
```

**Result:** `list_images()` returned real `ImageMetadata` for all 11 images
in the shared folder — no mocking, real Drive API round trip:

| filename | mime_type | size (bytes) | created_time (UTC) |
|---|---|---|---|
| C. annuum - posisi bunga menggantung_ warna bunga putih_ jumlah bunga 1 per ruas.jpg | image/jpeg | 2,227,927 | 2026-07-20 01:50:42.766 |
| cabai katokon - bentuk daun.jpg | image/jpeg | 4,690,785 | 2026-07-20 01:50:48.877 |
| cabai katokon - warna tangkai daun.jpg | image/jpeg | 4,334,188 | 2026-07-20 01:51:11.654 |
| cabai katokon - posisi bunga tegak_ jumlah bunga 3 per ruas.jpg | image/jpeg | 3,770,582 | 2026-07-20 01:51:06.835 |
| warna tangkai daun C.chinense dan C. annuum permukaan atas.jpg | image/jpeg | 1,845,863 | 2026-07-20 01:51:29.971 |
| tekstur daun cabai kopay (C.annuum - tdk berbulu) dan cabai gendot (C.pubescens - berbulu).jpg | image/jpeg | 4,667,130 | 2026-07-20 01:51:21.671 |
| cabai katokon - posisi bunga tegak_ jumlah bunga 2 per ruas.jpg | image/jpeg | 3,882,536 | 2026-07-20 01:51:01.096 |
| warna tangkai daun C. chinense dan C. annuum permukaan bawah.jpg | image/jpeg | 3,410,831 | 2026-07-20 01:51:26.322 |
| cabai katokon (C. chinense) - btk bh, warna bh_ posisi bh horizontal.jpg | image/jpeg | 4,139,637 | 2026-07-20 01:51:16.355 |
| cabai katokon - posisi bunga tegak_ jumlah bunga 1 per ruas_ warna bunga putih kehijauan.jpg | image/jpeg | 1,806,118 | 2026-07-20 01:50:53.182 |
| C. annuum - bentuk buah, warna bh_ posisi buah menggantung.jpg | image/jpeg | 98,952 | 2026-07-20 01:50:41.548 |

**Notes:**
- All 11 files are `image/*`, confirming the MIME-type filter behaves
  correctly against real, non-mocked Drive content.
- Filenames follow an informal Indonesian/scientific-mixed convention
  describing plant part + characteristic (e.g. "posisi bunga menggantung",
  "bentuk daun", "btk bh" = bentuk buah) — real signal for Fase 5's
  auxiliary filename-hint extraction, not just a hypothetical.
- Folder is flat, as designed — no subfolders encountered in this run.
