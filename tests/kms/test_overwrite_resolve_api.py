"""API tests for L3: POST /runs/v2/{run_id}/reviews/{item_id}/resolve role and validation testing (T-21).

Tests:
T-21: Endpoint forwards actor role; rejects non-curator on protected human review;
      validates payload format per category.
"""

from __future__ import annotations

import copy
import os
import pytest
from starlette.testclient import TestClient

from src.kms_api.app import create_app
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.image_storage import LocalCAS
from src.storage.repository import KmsRepository
from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_planner import DocumentPlanner
from src.storage.document_repository import DocumentRepository
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.migrate import migrate

pytestmark = pytest.mark.integration


@pytest.fixture
def api_client(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    import json
    tokens = {
        "reviewer-token-xyz-12345678901234567890": {"subject": "reviewer-1", "role": "reviewer"},
        "curator-token-xyz-12345678901234567890": {"subject": "curator-1", "role": "curator"},
    }
    media_dir = tmp_path / "media_test"
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
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)
    with TestClient(app) as client:
        yield client, settings


def test_t21_resolve_api_roles_and_validation(api_client):
    """T-21: API endpoint /runs/v2/{run_id}/reviews/{item_id}/resolve enforces roles and validates decisions."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    kms_repo = KmsRepository(engine)
    repo = DocumentRepository(engine)

    # 1. Setup existing document with HUMAN_REVIEW
    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    plant = PlantIdentity(id="plant_api_rawit", label="Cabai Rawit", identity_level="cultivar")
    doc_key = f"{plant.id}:{habitat.id}"

    sha1 = "9" * 64
    kms_repo.register_source(sha1, "cas:///sources/api1.xlsx", 1000, actor="test-curator")
    init_attr = AttributeValue(
        label="tinggi tanaman",
        value=80.0,
        value_type="number",
        unit="cm",
        resolution="HUMAN_REVIEW",
        current_source=CurrentSourceReference(
            source_ref="api1.xlsx", sheet="Sheet1", row=1, cell="A1", location_ref="loc_001"
        ),
    )
    doc_init = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[SamplingLocationDetail(location_ref="loc_001", raw_address="Sleman")],
        attributes={"attr_tinggi_tanaman": init_attr},
        media_refs=[],
        updated_by_run="run_api_init",
    )
    draft_init = DocumentDraft(
        run_id="run_api_init",
        source_filename="api1.xlsx",
        file_sha256=sha1,
        source_uri="cas:///sources/api1.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_init},
        reviews=[],
        base_versions={doc_key: 0},
    )
    staged = repo.stage(draft_init, expected_revision=0, actor="curator")
    repo.commit("run_api_init", staged["revision"], staged["payload_sha256"], actor="curator")

    # 2. Stage draft with OVERWRITE_BLOCKED (EXISTING_HUMAN_PROTECTED)
    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "85.0 cm",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft_update = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_api_update")
    assert len(draft_update.reviews) == 1
    item_id = draft_update.reviews[0].item_id

    sha2 = "8" * 64
    kms_repo.register_source(sha2, "cas:///sources/api2.xlsx", 1000, actor="test-curator")
    draft_update.source_uri = "cas:///sources/api2.xlsx"
    draft_update.file_sha256 = sha2
    draft_update.base_versions = {doc_key: 1}
    repo.stage(draft_update, expected_revision=0, actor="curator")

    # A. Reviewer token (role: reviewer) attempting to overwrite EXISTING_HUMAN_PROTECTED -> 409 Conflict
    rev_resp = client.post(
        f"/runs/v2/run_api_update/reviews/{item_id}/resolve",
        headers={"Authorization": "Bearer reviewer-token-xyz-12345678901234567890"},
        json={"action": "APPLY_INCOMING", "reason": "Attempt overwrite"},
    )
    assert rev_resp.status_code == 409
    assert "curator" in rev_resp.json()["detail"].lower()

    # B. Curator token (role: curator) without reason -> 422 InvalidState
    cur_no_reason = client.post(
        f"/runs/v2/run_api_update/reviews/{item_id}/resolve",
        headers={"Authorization": "Bearer curator-token-xyz-12345678901234567890"},
        json={"action": "APPLY_INCOMING", "reason": ""},
    )
    assert cur_no_reason.status_code == 422
    assert "reason" in cur_no_reason.json()["detail"].lower()

    # C. Curator token with reason -> 200 OK, approved
    cur_ok = client.post(
        f"/runs/v2/run_api_update/reviews/{item_id}/resolve",
        headers={"Authorization": "Bearer curator-token-xyz-12345678901234567890"},
        json={"action": "APPLY_INCOMING", "reason": "Verified field re-survey with agronomist"},
    )
    assert cur_ok.status_code == 200
    assert cur_ok.json()["status"] == "approved"
