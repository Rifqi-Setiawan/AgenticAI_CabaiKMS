# Drive Setup — service account + folder access for the Drive Crawler

The crawler (`src/agents/drive_crawler.py`) reads a Google Drive folder
read-only, using a service account rather than an interactive OAuth login
(no browser flow, works headless/in CI). This doc covers creating that
service account once and pointing `.env` at it.

## 1. Create (or reuse) a Google Cloud project

Any GCP project works — this is just a container for the service account
and API enablement, not something Drive users ever see.

1. Go to <https://console.cloud.google.com/>.
2. Create a new project (or select an existing one).

## 2. Enable the Google Drive API

1. In the project, go to **APIs & Services → Library**.
2. Search for "Google Drive API" and click **Enable**.

## 3. Create a service account

1. **APIs & Services → Credentials → Create Credentials → Service account**.
2. Give it any name (e.g. `drive-reader-bot`). No roles need to be granted
   at the project/IAM level — Drive file access is controlled by *sharing
   the folder* with the service account, not by GCP IAM roles.
3. Once created, open the service account, go to the **Keys** tab, **Add
   Key → Create new key → JSON**. This downloads a `credentials.json`
   file — treat it like a password (it grants read access to whatever
   you share with it).
4. Note the service account's **email** — it looks like
   `something@your-project.iam.gserviceaccount.com`. You'll need it in the
   next step. (It's also inside the downloaded JSON as `client_email`.)

## 4. Share the target Drive folder with the service account

A service account is not a person with their own Drive — it can only see
files/folders explicitly shared with it.

1. In Google Drive, right-click the folder containing the citra samples →
   **Share**.
2. Add the service account's email from step 3.
3. Role: **Viewer** is enough — the crawler only lists and reads metadata,
   it never writes.

## 5. Get the folder ID

Open the folder in Drive; the URL looks like:

```
https://drive.google.com/drive/folders/<FOLDER_ID>?usp=sharing
```

The folder ID is the segment between `/folders/` and `?`. You can also
paste the *whole URL* into `GOOGLE_DRIVE_FOLDER_ID` below —
`normalize_folder_id()` in `drive_crawler.py` strips the `?usp=sharing`
suffix (or extracts the ID from a full share URL) automatically, since
that's what actually ends up on the clipboard when you copy a Drive link.

## 6. Configure `.env`

```
GOOGLE_DRIVE_CREDENTIALS_PATH=credentials.json
GOOGLE_DRIVE_FOLDER_ID=<FOLDER_ID or the full share URL>
```

For the current Streamlit UI, also enter the folder URL/ID in the Input
page: a blank UI field deliberately skips vision, even when the environment
variable is set. Only service-account JSON credentials are implemented;
an OAuth client JSON is not interchangeable. Image classification additionally
needs `GOOGLE_API_KEY`; metadata listing alone does not call Gemini.

Put the downloaded JSON key file at the path you set above (the project
root's `.gitignore` already excludes `credentials.json` — never commit it).

## 7. Verify it works

```bash
python -c "from src.agents.drive_crawler import list_images; imgs = list_images(); print(len(imgs), 'images found'); [print(i.filename, i.mime_type, i.size) for i in imgs[:5]]"
```

If this prints real filenames from the shared folder, the setup is
correct. Common failures:

- **`DriveCrawlerError: credentials file not found`** — `GOOGLE_DRIVE_CREDENTIALS_PATH`
  points somewhere the JSON key isn't.
- **`HttpError 404`** — the folder either doesn't exist, the ID is wrong, or
  it was never shared with the service account's email (step 4).
- **0 images found, no error** — the folder was shared but is empty, or
  every file inside it is a non-`image/*` MIME type.
