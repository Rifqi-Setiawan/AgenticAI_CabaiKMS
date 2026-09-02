"""Fase 4 — Drive Crawler: list image files in a flat Google Drive folder.

Pure I/O, no semantic reasoning: authenticates with a read-only service
account, lists whatever is directly inside the target folder, keeps only
image/* files, and returns Fase 1's ImageMetadata contract. Which plant
part (daun/batang/buah/bunga) a photo shows is NOT decided here — that is
the Vision Agent's job, from the image's content, once it exists.

The Drive folder is assumed flat (see docs/DESIGN_DECISIONS.md (c)): the
`'{folder_id}' in parents` query only ever returns *direct* children, so
this module structurally never recurses. If a child happens to be a
folder anyway, it's skipped rather than walked into.
"""

from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv

from src.schema.contracts import ImageMetadata

load_dotenv()  # once at import, like src/llm/providers.py — see that module's
# docstring for why: calling load_dotenv() again inside a function would
# silently re-populate an env var a caller/test just deleted.

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DEFAULT_PAGE_SIZE = 100
GOOGLE_FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

_FOLDER_URL_RE = re.compile(r"drive\.google\.com/drive/folders/([a-zA-Z0-9_-]+)")


class DriveCrawlerError(Exception):
    """Raised when Drive credentials/configuration are missing or invalid."""


def normalize_folder_id(value: str) -> str:
    """Accepts either a bare folder id or a pasted share URL
    (`https://drive.google.com/drive/folders/<id>?usp=sharing`) — a share
    URL is what Drive's UI actually puts on the clipboard, so this is the
    common case, not an edge case."""
    value = value.strip()
    match = _FOLDER_URL_RE.search(value)
    if match:
        return match.group(1)
    return value.split("?")[0].rstrip("/")


def _load_credentials():
    from google.oauth2 import service_account

    creds_path = os.environ.get("GOOGLE_DRIVE_CREDENTIALS_PATH")
    if not creds_path:
        raise DriveCrawlerError("GOOGLE_DRIVE_CREDENTIALS_PATH is not set (.env)")
    if not os.path.exists(creds_path):
        raise DriveCrawlerError(f"credentials file not found: {creds_path}")
    try:
        return service_account.Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    except (ValueError, KeyError) as exc:
        raise DriveCrawlerError(f"invalid service account credentials file: {exc}") from exc


def get_drive_service(credentials: Any = None):
    from googleapiclient.discovery import build

    credentials = credentials or _load_credentials()
    return build("drive", "v3", credentials=credentials, cache_discovery=False)


def _resolve_folder_id(folder_id: str | None) -> str:
    folder_id = folder_id or os.environ.get("GOOGLE_DRIVE_FOLDER_ID")
    if not folder_id:
        raise DriveCrawlerError("GOOGLE_DRIVE_FOLDER_ID is not set (.env) and no folder_id given")
    return normalize_folder_id(folder_id)


def list_images(
    folder_id: str | None = None,
    *,
    service: Any = None,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> list[ImageMetadata]:
    """List every image/* file directly inside `folder_id` (default: read
    GOOGLE_DRIVE_FOLDER_ID from .env). Paginates automatically."""
    folder_id = _resolve_folder_id(folder_id)
    service = service or get_drive_service()

    query = f"'{folder_id}' in parents and trashed = false"
    fields = "nextPageToken, files(id, name, mimeType, size, createdTime)"

    images: list[ImageMetadata] = []
    page_token: str | None = None
    while True:
        response = (
            service.files()
            .list(q=query, fields=fields, pageSize=page_size, pageToken=page_token)
            .execute()
        )
        for f in response.get("files", []):
            mime_type = f.get("mimeType", "")
            if mime_type == GOOGLE_FOLDER_MIME_TYPE:
                continue  # a stray subfolder — skip it, never recurse into it
            if not mime_type.startswith("image/"):
                continue
            images.append(
                ImageMetadata(
                    file_id=f["id"],
                    filename=f["name"],
                    mime_type=mime_type,
                    size=int(f.get("size", 0) or 0),
                    created_time=f["createdTime"],
                )
            )
        page_token = response.get("nextPageToken")
        if not page_token:
            break

    return images


def crawl_to_state(folder_id: str | None = None, *, service: Any = None) -> dict[str, Any]:
    """GlobalState patch for an orchestrator node: {"image_metadata": [...]}."""
    return {"image_metadata": list_images(folder_id, service=service)}
