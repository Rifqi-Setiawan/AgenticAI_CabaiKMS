"""Tests for Round 4 API validation and UI integration (F-4, F-9)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
import pytest
from fastapi.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.config import Settings, get_settings
from src.storage.db import make_engine
from src.storage.document_repository import DocumentRepository
from src.storage.migrate import migrate
from src.integrations.candidates_ui import (
    resolve_candidate_api,
    set_document_habitat_api,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(tmp_path) -> tuple[TestClient, DocumentRepository, dict[str, str]]:
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL not configured")
    migrate(admin_url)
    tokens = {
        "r" * 40: {"subject": "reader-bob", "role": "reader"},
        "v" * 40: {"subject": "reviewer-dave", "role": "reviewer"},
        "c" * 40: {"subject": "curator-alice", "role": "curator"},
    }
    media_dir = tmp_path / "media_round4"
    media_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=admin_url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    from src.storage.repository import KmsRepository
    from src.storage.image_storage import LocalCAS
    repo = KmsRepository(engine)
    doc_repo = DocumentRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, doc_repository=doc_repo, blob_store=blob_store)
    client = TestClient(app)
    return client, doc_repo, {"reader": "r" * 40, "reviewer": "v" * 40, "curator": "c" * 40}


def test_n1_candidates_post_by_unauthorized_role_returns_403(api_client):
    """N1: POST /candidates with non-writer/reader role returns 403 Forbidden."""
    client, _, tokens = api_client
    reader_token = tokens["reader"]

    payload = {
        "asset_id": hashlib.sha256(b"asset_1").hexdigest(),
        "run_id": "run-01",
        "source_filename": "photo.png",
        "original_sha256": hashlib.sha256(b"orig_1").hexdigest(),
        "organ_part": "buah",
        "confidence": 0.9,
    }
    resp = client.post(
        "/candidates",
        json=payload,
        headers={"Authorization": f"Bearer {reader_token}"},
    )
    assert resp.status_code == 403


def test_n2_candidates_post_with_invalid_payload_returns_422(api_client):
    """N2: POST /candidates with missing fields or invalid format returns 422."""
    client, _, tokens = api_client
    curator_token = tokens["curator"]

    # Invalid: asset_id is not 64-hex, organ_part is invalid, confidence > 1.0
    bad_payload = {
        "asset_id": "not-a-sha256",
        "run_id": "run-01",
        "source_filename": "photo.png",
        "original_sha256": "short",
        "organ_part": "akar",  # Not valid organ part
        "confidence": 5.0,     # Out of bounds
    }
    resp = client.post(
        "/candidates",
        json=bad_payload,
        headers={"Authorization": f"Bearer {curator_token}"},
    )
    assert resp.status_code == 422


class StrictHttpxForwarderClient:
    """Mock KmsClient that forwards strictly using httpx kwargs without accepting json_body."""
    def __init__(self, test_client: TestClient, token: str):
        self.test_client = test_client
        self.token = token
        self.recorded_calls = []

    def request(self, method: str, path: str, **kwargs):
        if "json_body" in kwargs:
            raise TypeError("Client.request() got an unexpected keyword argument 'json_body'")
        self.recorded_calls.append({"method": method, "path": path, "kwargs": kwargs})
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self.token}"
        resp = self.test_client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
        return resp.json()


def test_u1_ui_bridge_uses_client_request(api_client):
    """U1: resolve_candidate_api and set_document_habitat_api use client.request()."""
    client, repo, tokens = api_client
    strict_client = StrictHttpxForwarderClient(client, tokens["curator"])

    # 1. Add candidate directly
    aid = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    sha = hashlib.sha256(uuid.uuid4().bytes).hexdigest()
    from src.storage.repository import KmsRepository
    kms_repo = KmsRepository(repo.engine)
    asset = {
        "id": aid,
        "original_sha256": sha,
        "transform_profile": "primary",
        "original_uri": f"cas:///orig/{aid}",
        "storage_uri": f"cas:///media/{aid}",
        "thumbnail_uri": f"cas:///thumb/{aid}",
        "image_sha256": sha,
        "thumbnail_sha256": sha,
        "mime_type": "image/webp",
        "file_size": 1000,
        "original_size": 1000,
        "thumbnail_size": 200,
        "width": 100,
        "height": 100,
    }
    kms_repo.register_asset(asset, actor="curator-alice")
    cand = repo.add_candidate(asset_id=aid, run_id="r1", source_filename="f.png", original_sha256=sha, organ_part="buah", confidence=0.9)

    # 2. Call resolve_candidate_api
    decision = {
        "action": "PROMOTE",
        "new_variety_name": f"Cabai U1 {uuid.uuid4().hex[:6]}",
        "reason": "Alasan valid promosi lebih dari 10 karakter",
    }
    res = resolve_candidate_api(cand["candidate_id"], decision, client=strict_client)
    assert res.get("status") == "PROMOTED"
    assert any(c["method"] == "POST" and f"/candidates/{cand['candidate_id']}/resolve" in c["path"] for c in strict_client.recorded_calls)


def test_u2_pages_kms_mounts_candidate_and_unknown_habitat_panels():
    """U2: pages/4_KMS.py imports and mounts render_candidates_panel and render_habitat_unknown_documents_panel."""
    with open("src/ui/pages/4_KMS.py", "r") as f:
        content = f.read()
    assert "render_candidates_panel" in content
    assert "render_habitat_unknown_documents_panel" in content


def test_u4_short_reason_fails_validation():
    """U4: Reason < 10 characters raises error or prevents API call."""
    from src.integrations.candidates_ui import validate_curator_reason
    assert validate_curator_reason("pendek") is False
    assert validate_curator_reason("Alasan yang cukup panjang dan valid") is True
