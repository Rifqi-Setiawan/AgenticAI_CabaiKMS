from __future__ import annotations

import pytest

from src.agents.drive_crawler import (
    DriveCrawlerError,
    crawl_to_state,
    list_images,
    normalize_folder_id,
)


class _FakeRequest:
    def __init__(self, page: dict):
        self._page = page

    def execute(self) -> dict:
        return self._page


class _FakeFilesResource:
    def __init__(self, pages: list[dict]):
        self._pages = pages
        self.calls: list[dict] = []

    def list(self, **kwargs) -> _FakeRequest:
        self.calls.append(kwargs)
        return _FakeRequest(self._pages[len(self.calls) - 1])


class _FakeService:
    def __init__(self, pages: list[dict]):
        self._files = _FakeFilesResource(pages)

    def files(self) -> _FakeFilesResource:
        return self._files


def _file(id_, name, mime, size="1024", created="2026-06-01T10:00:00.000Z"):
    return {"id": id_, "name": name, "mimeType": mime, "size": size, "createdTime": created}


class TestNormalizeFolderId:
    def test_bare_id_unchanged(self):
        assert normalize_folder_id("1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g") == "1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g"

    def test_id_with_query_suffix_is_stripped(self):
        assert normalize_folder_id("1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g?usp=sharing") == "1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g"

    def test_full_share_url_extracts_id(self):
        url = "https://drive.google.com/drive/folders/1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g?usp=sharing"
        assert normalize_folder_id(url) == "1G1DG4qfT_-EhJ_D7XZvnK1Kw1EGu8t2g"

    def test_trailing_slash_is_stripped(self):
        assert normalize_folder_id("abc123/") == "abc123"


class TestListImages:
    def test_returns_only_image_files(self):
        page = {
            "files": [
                _file("f1", "daun1.jpg", "image/jpeg"),
                _file("f2", "notes.pdf", "application/pdf"),
                _file("f3", "batang1.png", "image/png"),
            ]
        }
        service = _FakeService([page])
        images = list_images("folder123", service=service)
        assert {img.filename for img in images} == {"daun1.jpg", "batang1.png"}

    def test_subfolder_is_skipped_not_recursed(self):
        page = {
            "files": [
                _file("f1", "daun1.jpg", "image/jpeg"),
                {"id": "sub1", "name": "stray subfolder", "mimeType": "application/vnd.google-apps.folder"},
            ]
        }
        service = _FakeService([page])
        images = list_images("folder123", service=service)
        assert len(images) == 1
        assert images[0].filename == "daun1.jpg"
        # exactly one list() call total — a subfolder must never trigger a
        # second, recursive listing call
        assert len(service.files().calls) == 1

    def test_paginates_across_multiple_pages(self):
        page1 = {"files": [_file("f1", "a.jpg", "image/jpeg")], "nextPageToken": "TOKEN2"}
        page2 = {"files": [_file("f2", "b.jpg", "image/jpeg")]}
        service = _FakeService([page1, page2])

        images = list_images("folder123", service=service)

        assert {img.filename for img in images} == {"a.jpg", "b.jpg"}
        calls = service.files().calls
        assert len(calls) == 2
        assert calls[0]["pageToken"] is None
        assert calls[1]["pageToken"] == "TOKEN2"

    def test_query_scopes_to_direct_children_of_folder(self):
        service = _FakeService([{"files": []}])
        list_images("folder123", service=service)
        query = service.files().calls[0]["q"]
        assert "'folder123' in parents" in query
        assert "trashed = false" in query

    def test_image_metadata_fields_populated_correctly(self):
        page = {"files": [_file("f1", "daun1.jpg", "image/jpeg", size="204800", created="2026-06-01T10:00:00.000Z")]}
        service = _FakeService([page])
        images = list_images("folder123", service=service)
        img = images[0]
        assert img.file_id == "f1"
        assert img.filename == "daun1.jpg"
        assert img.mime_type == "image/jpeg"
        assert img.size == 204800
        assert img.created_time.year == 2026

    def test_missing_size_defaults_to_zero(self):
        f = {"id": "f1", "name": "daun1.jpg", "mimeType": "image/jpeg", "createdTime": "2026-06-01T10:00:00.000Z"}
        service = _FakeService([{"files": [f]}])
        images = list_images("folder123", service=service)
        assert images[0].size == 0

    def test_no_folder_id_and_no_env_var_raises(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DRIVE_FOLDER_ID", raising=False)
        with pytest.raises(DriveCrawlerError):
            list_images(None, service=_FakeService([{"files": []}]))

    def test_env_var_folder_id_is_used_and_normalized(self, monkeypatch):
        monkeypatch.setenv("GOOGLE_DRIVE_FOLDER_ID", "folder123?usp=sharing")
        service = _FakeService([{"files": []}])
        list_images(None, service=service)
        assert "'folder123' in parents" in service.files().calls[0]["q"]

    def test_missing_credentials_path_raises_when_no_service_given(self, monkeypatch):
        monkeypatch.delenv("GOOGLE_DRIVE_CREDENTIALS_PATH", raising=False)
        with pytest.raises(DriveCrawlerError):
            list_images("folder123")  # no service injected -> tries to build a real one


class TestCrawlToState:
    def test_wraps_result_into_state_patch(self):
        page = {"files": [_file("f1", "daun1.jpg", "image/jpeg")]}
        service = _FakeService([page])
        patch = crawl_to_state("folder123", service=service)
        assert list(patch.keys()) == ["image_metadata"]
        assert len(patch["image_metadata"]) == 1
