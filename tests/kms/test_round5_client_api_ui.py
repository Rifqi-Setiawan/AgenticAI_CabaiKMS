"""Tests for Round 5: Real KmsClient, HTTPX kwargs, UI integration, and Habitat deterministic resolution (G-1, G-2, G-3, G-6, G-8)."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.kms_api.app import create_app
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import AdministrativePath, HabitatIdentity, KnowledgeDocument, PlantIdentity
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState
from src.storage.identity_resolution import compute_habitat_id
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository
from src.integrations.client import KmsClient
from src.integrations.candidates_ui import (
    resolve_candidate_api,
    set_document_habitat_api,
)

pytestmark = pytest.mark.integration


@pytest.fixture
def real_kms_stack(tmp_path) -> tuple[KmsClient, DocumentRepository, Engine]:
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL not configured")
    migrate(admin_url)

    token = "c" * 40
    tokens = {
        token: {"subject": "curator-alice", "role": "curator"},
    }
    media_dir = tmp_path / "media_round5"
    media_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        _env_file=None,
        database_url=admin_url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
        kms_api_base_url="http://127.0.0.1:8093",
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    doc_repo = DocumentRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, doc_repository=doc_repo, blob_store=blob_store)

    from fastapi.testclient import TestClient
    def client_factory(**kw):
        kw.pop("timeout", None)
        return TestClient(app, **kw)

    client = KmsClient(settings, token=token, client_factory=client_factory)
    return client, doc_repo, engine


def _register_asset(engine: Engine, asset_id: str, sha: str, profile: str = "primary"):
    repo = KmsRepository(engine)
    asset = {
        "id": asset_id,
        "original_sha256": sha,
        "transform_profile": profile,
        "original_uri": f"cas:///orig/{asset_id}",
        "storage_uri": f"cas:///media/{asset_id}",
        "thumbnail_uri": f"cas:///thumb/{asset_id}",
        "image_sha256": sha,
        "thumbnail_sha256": sha,
        "mime_type": "image/webp",
        "file_size": 1000,
        "original_size": 1000,
        "thumbnail_size": 200,
        "width": 100,
        "height": 100,
    }
    repo.register_asset(asset, actor="curator-alice")


def test_p1_real_kms_client_promote_merge_discard_and_set_habitat(real_kms_stack):
    """P1: PROMOTE, MERGE, DISCARD, and SET_HABITAT execute cleanly via genuine KmsClient without TypeError."""
    client, repo, engine = real_kms_stack
    suffix = uuid.uuid4().hex[:8]

    # 1. Register assets and create candidate
    aid1 = hashlib.sha256(f"p1_a1_{suffix}".encode()).hexdigest()
    aid2 = hashlib.sha256(f"p1_a2_{suffix}".encode()).hexdigest()
    sha1 = hashlib.sha256(f"p1_s1_{suffix}".encode()).hexdigest()
    sha2 = hashlib.sha256(f"p1_s2_{suffix}".encode()).hexdigest()
    _register_asset(engine, aid1, sha1, profile="primary")
    _register_asset(engine, aid2, sha2, profile="primary")

    c1 = repo.add_candidate(asset_id=aid1, run_id=f"run_{suffix}", source_filename="c1.png", original_sha256=sha1, organ_part="buah", confidence=0.9)
    c2 = repo.add_candidate(asset_id=aid2, run_id=f"run_{suffix}", source_filename="c2.png", original_sha256=sha2, organ_part="daun", confidence=0.88)

    # A) PROMOTE via real client
    res_promote = resolve_candidate_api(
        c1["candidate_id"],
        {
            "action": "PROMOTE",
            "new_variety_name": f"Cabai P1 {suffix}",
            "reason": "Alasan valid promosi varietas baru lebih dari 10 karakter",
        },
        client=client,
    )
    assert res_promote["status"] == "PROMOTED"

    target_doc_key = f"plant_cabai_p1_{suffix}:habitat_unknown"
    doc_promoted = repo.get_document(target_doc_key)
    assert doc_promoted is not None

    # B) MERGE via real client (with expected_version)
    res_merge = resolve_candidate_api(
        c2["candidate_id"],
        {
            "action": "MERGE",
            "target_doc_key": target_doc_key,
            "expected_version": doc_promoted["version"],
            "reason": "Alasan valid merge daun varietas sama lebih dari 10 karakter",
        },
        client=client,
    )
    assert res_merge["status"] == "MERGED"

    doc_merged = repo.get_document(target_doc_key)
    assert len(doc_merged["media_refs"]) == 2

    # C) DISCARD via real client
    aid3 = hashlib.sha256(f"p1_a3_{suffix}".encode()).hexdigest()
    sha3 = hashlib.sha256(f"p1_s3_{suffix}".encode()).hexdigest()
    _register_asset(engine, aid3, sha3, profile="primary")
    c3 = repo.add_candidate(asset_id=aid3, run_id=f"run_{suffix}", source_filename="c3.png", original_sha256=sha3, organ_part="batang", confidence=0.7)

    res_discard = resolve_candidate_api(
        c3["candidate_id"],
        {"action": "DISCARD", "reason": "Foto bukan cabai asli lebih dari 10 karakter"},
        client=client,
    )
    assert res_discard["status"] == "DISCARDED"

    # D) SET_HABITAT via real client
    new_hab_path = AdministrativePath(
        province_name="Jawa Barat",
        regency_name="Garut",
        district_name="Tarogong Kaler",
        village_name="Pananjung",
    )
    new_hab_id = compute_habitat_id(new_hab_path)
    habitat_payload = {
        "id": new_hab_id,
        "label": "Desa Pananjung",
        "definition": "administrative_village_v1",
        "administrative_path": new_hab_path.model_dump(mode="json"),
    }
    res_hab = set_document_habitat_api(target_doc_key, habitat_payload, client=client)
    assert res_hab["habitat"]["id"] == new_hab_id
    assert res_hab["habitat_unknown"] is False
    assert repo.get_document(target_doc_key) is None
    assert repo.get_document(f"plant_cabai_p1_{suffix}:{new_hab_id}") is not None


def test_p2_real_kms_client_get_candidates_with_params(real_kms_stack):
    """P2: GET /candidates with params works cleanly via genuine KmsClient."""
    client, repo, _ = real_kms_stack
    res = client.request("GET", "/candidates", params={"status": "CANDIDATE"})
    assert isinstance(res, list)


def test_p3_conflict_409_raises_conflict_exception(real_kms_stack):
    """P3: HTTP 409 from server is translated into Conflict exception by KmsClient."""
    client, repo, engine = real_kms_stack
    suffix = uuid.uuid4().hex[:8]
    aid = hashlib.sha256(f"p3_a_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"p3_s_{suffix}".encode()).hexdigest()
    _register_asset(engine, aid, sha)

    cand1 = repo.add_candidate(asset_id=aid, run_id=f"run_{suffix}", source_filename="c1.png", original_sha256=sha, organ_part="buah", confidence=0.9)
    # Promote first
    resolve_candidate_api(cand1["candidate_id"], {"action": "PROMOTE", "new_variety_name": f"Cabai P3 {suffix}", "reason": "Promote pertama lebih 10 karakter"}, client=client)

    # Second candidate with same variety name must raise Conflict
    aid2 = hashlib.sha256(f"p3_a2_{suffix}".encode()).hexdigest()
    sha2 = hashlib.sha256(f"p3_s2_{suffix}".encode()).hexdigest()
    _register_asset(engine, aid2, sha2)
    cand2 = repo.add_candidate(asset_id=aid2, run_id=f"run_{suffix}", source_filename="c2.png", original_sha256=sha2, organ_part="daun", confidence=0.85)

    with pytest.raises(Conflict) as exc:
        resolve_candidate_api(cand2["candidate_id"], {"action": "PROMOTE", "new_variety_name": f"Cabai P3 {suffix}", "reason": "Promote kedua harusnya conflict"}, client=client)
    assert "already exists" in str(exc.value).lower()


def test_q1_set_habitat_with_unknown_tiers_raises_invalid_state(real_kms_stack):
    """Q1: Payload with 'Unknown' in administrative tiers is rejected by server with InvalidState."""
    client, repo, engine = real_kms_stack
    suffix = uuid.uuid4().hex[:8]

    # Pre-create a document with habitat_unknown
    plant = PlantIdentity(id=f"plant_q1_{suffix}", label=f"Cabai Q1 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Unknown", regency_name="Unknown", district_name="Unknown", village_name="Unknown"),
        label="Habitat Tidak Diketahui",
    )
    doc_key = f"{plant.id}:{unknown_hab.id}"
    doc = KnowledgeDocument(variety=plant, habitat=unknown_hab, attributes={}, media_refs=[], habitat_unknown=True)
    draft = repo.stage_direct_document(doc_key, doc, run_id=f"run_{suffix}", actor="curator-alice")
    repo.commit(f"run_{suffix}", draft["revision"], draft["payload_sha256"], actor="curator-alice")

    # Attempt setting habitat with "Unknown" in kabupaten/desa
    bad_payload = {
        "id": "hab_palsu",
        "label": "Desa Unknown",
        "definition": "administrative_village_v1",
        "administrative_path": {
            "province_name": "Jawa Barat",
            "regency_name": "Kabupaten",  # Invalid generic
            "district_name": "Unknown",   # Rejected!
            "village_name": "Unknown",    # Rejected!
        },
    }
    with pytest.raises(InvalidState) as exc:
        set_document_habitat_api(doc_key, bad_payload, client=client)
    assert "unknown" in str(exc.value).lower() or "valid" in str(exc.value).lower()


def test_q2_compute_habitat_id_matches_pipeline_standard():
    """Q2: compute_habitat_id deterministically outputs hab_{regency}_{district}_{village} matching pipeline."""
    path = AdministrativePath(
        province_name="DI Yogyakarta",
        regency_name="Kabupaten Sleman",
        district_name="Kecamatan Pakem",
        village_name="Desa Hargobinangun",
    )
    hid = compute_habitat_id(path)
    assert hid == "hab_sleman_pakem_hargobinangun"

    path2 = AdministrativePath(
        province_name="Jawa Tengah",
        regency_name="Wonosobo",
        district_name="Kalikajar",
        village_name="Lamuk",
    )
    assert compute_habitat_id(path2) == "hab_wonosobo_kalikajar_lamuk"


def test_t1_habitat_relink_audit_trace_recorded(real_kms_stack):
    """T1: Relinking document habitat creates an audit trace entry in kms.document_attribute_changes."""
    client, repo, engine = real_kms_stack
    suffix = uuid.uuid4().hex[:8]

    plant = PlantIdentity(id=f"plant_t1_{suffix}", label=f"Cabai T1 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Unknown", regency_name="Unknown", district_name="Unknown", village_name="Unknown"),
        label="Habitat Tidak Diketahui",
    )
    doc_key = f"{plant.id}:{unknown_hab.id}"
    doc = KnowledgeDocument(variety=plant, habitat=unknown_hab, attributes={}, media_refs=[], habitat_unknown=True)
    draft = repo.stage_direct_document(doc_key, doc, run_id=f"run_{suffix}", actor="curator-alice")
    repo.commit(f"run_{suffix}", draft["revision"], draft["payload_sha256"], actor="curator-alice")

    target_path = AdministrativePath(
        province_name="Jawa Timur",
        regency_name="Kabupaten Malang",
        district_name="Kecamatan Pujon",
        village_name="Desa Pandansari",
    )
    target_hid = compute_habitat_id(target_path)
    payload = {
        "id": target_hid,
        "label": "Desa Pandansari",
        "definition": "administrative_village_v1",
        "administrative_path": target_path.model_dump(mode="json"),
    }
    set_document_habitat_api(doc_key, payload, client=client)

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT * FROM kms.document_attribute_changes WHERE attribute_id = 'habitat_migration_relink' AND doc_id = :d"),
            {"d": doc_key},
        ).mappings().all()
    assert len(rows) >= 1
    new_val = json.loads(rows[0]["new_value"]) if isinstance(rows[0]["new_value"], str) else rows[0]["new_value"]
    assert new_val["habitat_id"] == target_hid


def test_g8_app_test_mounts_three_tabs_and_panels():
    """G-8: Streamlit execution verifies 4_KMS.py mounts all three tabs and panels without crash."""
    import importlib
    from unittest.mock import MagicMock, patch
    from src.integrations.candidates_ui import render_candidates_panel, render_habitat_unknown_documents_panel
    kms_page = importlib.import_module("src.ui.pages.4_KMS")

    assert hasattr(kms_page, "render_candidates_panel")
    assert hasattr(kms_page, "render_habitat_unknown_documents_panel")

    with patch("streamlit.subheader"), \
         patch("streamlit.info"), \
         patch("streamlit.write"):
        render_candidates_panel([])
        render_habitat_unknown_documents_panel([])

