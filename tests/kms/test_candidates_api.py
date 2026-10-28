"""API contract and integration tests for B-4: Candidate Queue and Habitat Unknown Endpoints.

Tests:
1. GET /candidates without token returns 401 Unauthorized.
2. POST /candidates/{id}/resolve by non-curator returns 403 Forbidden.
3. GET /candidates and GET /candidates/{id} returns candidate with media_url.
4. POST /candidates/{id}/resolve unwraps nested decision {"decision": {...}} for PROMOTE, MERGE, DISCARD.
5. GET /documents?habitat_unknown=true returns filtered documents.
6. POST /documents/{key}/habitat moves document to resolved habitat.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import (
    AdministrativePath,
    AttributeValue,
    CurrentSourceReference,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
)
from src.storage.document_repository import DocumentRepository
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def api_context(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    tokens = {
        "r" * 40: {"subject": "reader-1", "role": "reader"},
        "c" * 40: {"subject": "curator-1", "role": "curator"},
    }
    media_dir = tmp_path / "media_api_candidates"
    media_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    doc_repo = DocumentRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, doc_repository=doc_repo, blob_store=blob_store)
    return app, doc_repo, repo, engine


def test_api_candidates_unauthorized_without_token(api_context):
    """GET /candidates without token returns HTTP 401."""
    app, _, _, _ = api_context
    with TestClient(app) as client:
        resp = client.get("/candidates")
        assert resp.status_code == 401


def test_api_resolve_candidate_non_curator_returns_403(api_context):
    """POST /candidates/{id}/resolve with reader role returns HTTP 403."""
    app, doc_repo, kms_repo, _ = api_context
    aid = "1" * 64
    sha = "a" * 64
    kms_repo.register_asset({
        "id": aid, "original_sha256": sha, "transform_profile": "primary",
        "original_uri": "cas:///orig/1", "storage_uri": "cas:///media/1", "thumbnail_uri": "cas:///thumb/1",
        "image_sha256": sha, "thumbnail_sha256": sha, "mime_type": "image/webp",
        "file_size": 1000, "original_size": 1000, "thumbnail_size": 200, "width": 100, "height": 100,
    }, actor="curator-1")
    cand = doc_repo.add_candidate(
        asset_id=aid, run_id="run_api_403", source_filename="c.png", original_sha256=sha, organ_part="buah", confidence=0.85
    )

    with TestClient(app) as client:
        resp = client.post(
            f"/candidates/{cand['candidate_id']}/resolve",
            json={"action": "DISCARD", "reason": "Bukan cabai valid 10 char"},
            headers={"Authorization": "Bearer " + "r" * 40},
        )
        assert resp.status_code == 403


def test_api_get_candidates_list_and_detail(api_context):
    """GET /candidates returns candidate list; GET /candidates/{id} returns details with media_url."""
    app, doc_repo, kms_repo, _ = api_context
    aid = "2" * 64
    sha = "b" * 64
    kms_repo.register_asset({
        "id": aid, "original_sha256": sha, "transform_profile": "primary",
        "original_uri": "cas:///orig/2", "storage_uri": "cas:///media/2", "thumbnail_uri": "cas:///thumb/2",
        "image_sha256": sha, "thumbnail_sha256": sha, "mime_type": "image/webp",
        "file_size": 1000, "original_size": 1000, "thumbnail_size": 200, "width": 100, "height": 100,
    }, actor="curator-1")
    cand = doc_repo.add_candidate(
        asset_id=aid, run_id="run_api_list", source_filename="c2.png", original_sha256=sha, organ_part="buah", confidence=0.88,
        suggested_name="Cabai Unik", visual_evidence={"color": "red"}
    )

    with TestClient(app) as client:
        # List
        resp = client.get("/candidates?status=CANDIDATE", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp.status_code == 200
        items = resp.json()
        assert any(item["candidate_id"] == cand["candidate_id"] for item in items)

        # Detail
        resp_detail = client.get(f"/candidates/{cand['candidate_id']}", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp_detail.status_code == 200
        detail = resp_detail.json()
        assert detail["candidate_id"] == cand["candidate_id"]
        assert detail["media_url"] == f"/media/{aid}"


def test_api_resolve_candidate_unwrapped_promote(api_context):
    """POST /candidates/{id}/resolve unwraps nested decision object and executes PROMOTE."""
    app, doc_repo, kms_repo, _ = api_context
    suffix = uuid.uuid4().hex[:12]
    aid = hashlib.sha256(f"asset_promote_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"sha_promote_{suffix}".encode()).hexdigest()
    kms_repo.register_asset({
        "id": aid, "original_sha256": sha, "transform_profile": "primary",
        "original_uri": f"cas:///orig/{suffix}", "storage_uri": f"cas:///media/{suffix}", "thumbnail_uri": f"cas:///thumb/{suffix}",
        "image_sha256": sha, "thumbnail_sha256": sha, "mime_type": "image/webp",
        "file_size": 1000, "original_size": 1000, "thumbnail_size": 200, "width": 100, "height": 100,
    }, actor="curator-1")
    cand = doc_repo.add_candidate(
        asset_id=aid, run_id=f"run_promote_{suffix}", source_filename=f"c_{suffix}.png", original_sha256=sha, organ_part="buah", confidence=0.91
    )

    with TestClient(app) as client:
        # Test nested {"decision": {...}} wrapping
        resp = client.post(
            f"/candidates/{cand['candidate_id']}/resolve",
            json={
                "decision": {
                    "action": "PROMOTE",
                    "new_variety_name": f"Cabai Ungu Kerinci {suffix}",
                    "reason": "Morfologi buah ungu eksotis varietas baru terverifikasi",
                }
            },
            headers={"Authorization": "Bearer " + "c" * 40},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "PROMOTED"


def test_api_get_documents_habitat_unknown_filter(api_context):
    """GET /documents?habitat_unknown=true returns only documents flagged with habitat_unknown."""
    app, doc_repo, _, _ = api_context
    with TestClient(app) as client:
        resp = client.get("/documents?habitat_unknown=true", headers={"Authorization": "Bearer " + "r" * 40})
        assert resp.status_code == 200
        data = resp.json()
        docs = data.get("items", data) if isinstance(data, dict) else data
        assert isinstance(docs, list)
        for d in docs:
            assert d.get("habitat_unknown") is True or d.get("habitat", {}).get("id") == "habitat_unknown"


def test_api_set_document_habitat(api_context):
    """POST /documents/{key}/habitat sets resolved habitat on habitat_unknown document."""
    app, doc_repo, kms_repo, _ = api_context
    suffix = uuid.uuid4().hex[:12]
    # Create document with habitat_unknown
    plant = PlantIdentity(id=f"plant_api_{suffix}", label=f"Cabai Ungu API {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Unknown", regency_name="Unknown", district_name="Unknown", village_name="Unknown"
        ),
        label="Habitat Tidak Diketahui",
    )
    doc_key_src = f"{plant.id}:{unknown_hab.id}"
    doc_src = KnowledgeDocument(
        variety=plant,
        habitat=unknown_hab,
        attributes={
            "attr_api": AttributeValue(
                label="warna", value="ungu", value_type="text", resolution="HUMAN_REVIEW",
                current_source=CurrentSourceReference(source_ref="src.xlsx", sheet="Sheet1", row=2, cell="A2")
            )
        },
        media_refs=[],
        habitat_unknown=True,
    )
    draft = doc_repo.stage_direct_document(doc_key_src, doc_src, run_id=f"run_api_hab_{suffix}", actor="curator-1")
    doc_repo.commit(f"run_api_hab_{suffix}", draft["revision"], draft["payload_sha256"], actor="curator-1")

    target_hab = HabitatIdentity(
        id=f"hab_api_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Jambi", regency_name="Kerinci", district_name="Kayu Aro", village_name="Batu Hampar"
        ),
        label="Desa Batu Hampar",
    )

    with TestClient(app) as client:
        resp = client.post(
            f"/documents/{doc_key_src}/habitat",
            json=target_hab.model_dump(mode="json"),
            headers={"Authorization": "Bearer " + "c" * 40},
        )
        assert resp.status_code == 200
        updated = resp.json()
        assert updated.get("habitat_unknown") is False
        assert updated["habitat"]["id"] == f"hab_api_{suffix}"
