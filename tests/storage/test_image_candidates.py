"""Unit and integration tests for B-3: Image Candidate Queue and Additive Migration 0004 (K1..K11).

Tests:
K1: add_candidate is idempotent on asset_id.
K2: PROMOTE without habitat creates document with habitat_unknown=True and sentinel habitat.
K3: PROMOTE with habitat creates document bound to specified administrative habitat.
K4: MERGE links candidate image into existing KnowledgeDocument.media_refs.
K5: DISCARD records entry in kms.discarded_images and prevents duplicate candidacy.
K6: Non-curator resolving candidate raises Conflict/Forbidden.
K7: Duplicate resolution on already decided candidate raises Conflict.
K8: SET_HABITAT moves/merges document to real variety:habitat key without loss of attributes/media.
K9: Candidates do not expire and persist indefinitely.
K10: No automatic clustering: two distinct similar images create two individual candidate rows.
K11: Migration 0004 is additive, idempotent, and validated by /readyz.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
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
from src.storage.errors import Conflict, InvalidState, NotFound
from src.storage.image_storage import LocalCAS
from src.storage.migrate import MIGRATIONS, migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def db() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)
    return make_engine(Settings(_env_file=None, database_url=url))


def _register_asset(engine: Engine, asset_id: str, sha: str):
    repo = KmsRepository(engine)
    asset = {
        "id": asset_id,
        "original_sha256": sha,
        "transform_profile": "primary",
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
    repo.register_asset(asset, actor="curator-1")


def test_k1_add_candidate_idempotent(db: Engine):
    """K1: add_candidate with same asset_id returns existing candidate idempotently."""
    repo = DocumentRepository(db)
    aid = "a" * 64
    sha = "1" * 64
    _register_asset(db, aid, sha)

    c1 = repo.add_candidate(
        asset_id=aid,
        run_id="run_k1",
        source_filename="cabe_unik_01.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.88,
        suggested_name="Cabai Hiyung",
        visual_evidence={"color": "orange", "shape": "conical"},
    )
    assert c1["status"] == "CANDIDATE"
    assert c1["asset_id"] == aid

    # Second call must return identical candidate
    c2 = repo.add_candidate(
        asset_id=aid,
        run_id="run_k1_dup",
        source_filename="cabe_unik_01.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.88,
    )
    assert c2["candidate_id"] == c1["candidate_id"]


def test_k2_promote_without_habitat_creates_habitat_unknown_doc(db: Engine):
    """K2: PROMOTE without habitat creates KnowledgeDocument with habitat_unknown=True."""
    repo = DocumentRepository(db)
    aid = "b" * 64
    sha = "2" * 64
    _register_asset(db, aid, sha)

    c = repo.add_candidate(
        asset_id=aid,
        run_id="run_k2",
        source_filename="cabe_k2.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.85,
    )

    decision = {
        "action": "PROMOTE",
        "new_variety_name": "Cabai Putih Kudeti",
        "reason": "Morfologi buah putih tegak spesimen baru terverifikasi",
    }
    resolved = repo.resolve_candidate(c["candidate_id"], decision, actor="curator-1", actor_role="curator")
    assert resolved["status"] == "PROMOTED"

    # Verify document was created with habitat_unknown flag
    unknown_docs = repo.list_documents(habitat_unknown=True)
    matching = [d for d in unknown_docs if d["variety"]["label"] == "Cabai Putih Kudeti"]
    assert len(matching) == 1
    doc = matching[0]
    assert doc.get("habitat_unknown") is True
    assert doc["habitat"]["id"] == "habitat_unknown"
    assert len(doc["media_refs"]) == 1
    assert doc["media_refs"][0]["asset_id"] == aid


def test_k3_promote_with_habitat_creates_bound_doc(db: Engine):
    """K3: PROMOTE with explicit habitat creates KnowledgeDocument bound to that habitat."""
    repo = DocumentRepository(db)
    aid = "c" * 64
    sha = "3" * 64
    _register_asset(db, aid, sha)

    c = repo.add_candidate(
        asset_id=aid,
        run_id="run_k3",
        source_filename="cabe_k3.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.89,
    )

    habitat = HabitatIdentity(
        id="hab_k3",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Jawa Barat",
            regency_name="Garut",
            district_name="Tarogong",
            village_name="Pananjung",
        ),
        label="Desa Pananjung",
    )

    decision = {
        "action": "PROMOTE",
        "new_variety_name": "Cabai Garut Super",
        "habitat": habitat.model_dump(mode="json"),
        "reason": "Varietas baru ditemukan di kebun Desa Pananjung Garut",
    }
    resolved = repo.resolve_candidate(c["candidate_id"], decision, actor="curator-1", actor_role="curator")
    assert resolved["status"] == "PROMOTED"

    doc = repo.get_document(f"plant_cabai_garut_super:hab_k3")
    assert doc is not None
    assert doc.get("habitat_unknown") is False
    assert doc["habitat"]["id"] == "hab_k3"
    assert doc["media_refs"][0]["asset_id"] == aid


def test_k4_merge_links_media_to_existing_doc(db: Engine):
    """K4: MERGE links candidate image into an existing KnowledgeDocument's media_refs."""
    repo = DocumentRepository(db)

    # Setup base existing doc
    plant = PlantIdentity(id="plant_k4", label="Cabai Rawit", identity_level="cultivar")
    habitat = HabitatIdentity(
        id="hab_k4",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="DIY",
            regency_name="Sleman",
            district_name="Pakem",
            village_name="Hargobinangun",
        ),
        label="Desa Hargobinangun",
    )
    doc_key = f"{plant.id}:{habitat.id}"
    base_doc = KnowledgeDocument(
        variety=plant,
        habitat=habitat,
        attributes={
            "attr_tinggi": AttributeValue(
                label="tinggi",
                value=75.0,
                value_type="number",
                unit="cm",
                resolution="AUTO_ACCEPT",
                current_source=CurrentSourceReference(source_ref="k4.xlsx", sheet="Sheet1", row=2, cell="A2"),
            )
        },
        media_refs=[],
    )
    kms_repo = KmsRepository(db)
    kms_repo.register_source("4" * 64, "cas:///sources/k4.xlsx", 1000, actor="curator-1")
    draft = repo.stage_direct_document(doc_key, base_doc, run_id="run_k4_base", actor="curator-1")
    repo.commit("run_k4_base", draft["revision"], draft["payload_sha256"], actor="curator-1")

    # Add candidate
    aid = "d" * 64
    sha = "5" * 64
    _register_asset(db, aid, sha)
    cand = repo.add_candidate(
        asset_id=aid,
        run_id="run_k4_cand",
        source_filename="rawit_tambahan.png",
        original_sha256=sha,
        organ_part="daun",
        confidence=0.86,
    )

    decision = {
        "action": "MERGE",
        "target_doc_key": doc_key,
        "reason": "Citra daun varietas Cabai Rawit di habitat Hargobinangun",
    }
    resolved = repo.resolve_candidate(cand["candidate_id"], decision, actor="curator-1", actor_role="curator")
    assert resolved["status"] == "MERGED"

    updated_doc = repo.get_document(doc_key)
    assert len(updated_doc["media_refs"]) == 1
    assert updated_doc["media_refs"][0]["asset_id"] == aid


def test_k5_discard_records_discarded_image(db: Engine):
    """K5: DISCARD records entry in kms.discarded_images and suppresses future candidate creation."""
    repo = DocumentRepository(db)
    aid = "e" * 64
    sha = "6" * 64
    _register_asset(db, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid,
        run_id="run_k5",
        source_filename="bukan_cabe.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.82,
    )

    decision = {
        "action": "DISCARD",
        "reason": "Citra adalah tanaman tomat bukan tanaman cabai sama sekali",
    }
    resolved = repo.resolve_candidate(cand["candidate_id"], decision, actor="curator-1", actor_role="curator")
    assert resolved["status"] == "DISCARDED"

    # Verify kms.discarded_images has row
    with db.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM kms.discarded_images WHERE original_sha256 = :s"),
            {"s": sha},
        ).mappings().first()
    assert row is not None
    assert row["reason"] == decision["reason"]

    # Re-adding same image sha should return None or be skipped
    c_new = repo.add_candidate(
        asset_id=aid,
        run_id="run_k5_re",
        source_filename="bukan_cabe.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.82,
    )
    assert c_new is None or c_new.get("status") == "DISCARDED"


def test_k6_non_curator_raises_conflict(db: Engine):
    """K6: Resolving candidate without curator role raises Conflict."""
    repo = DocumentRepository(db)
    aid = "f" * 64
    sha = "7" * 64
    _register_asset(db, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid,
        run_id="run_k6",
        source_filename="cand_k6.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.88,
    )

    with pytest.raises(Conflict):
        repo.resolve_candidate(
            cand["candidate_id"],
            {"action": "DISCARD", "reason": "Bukan cabai valid 10 char"},
            actor="reader-1",
            actor_role="reader",
        )


def test_k7_duplicate_resolution_raises_conflict(db: Engine):
    """K7: Duplicate resolution on already decided candidate raises Conflict."""
    repo = DocumentRepository(db)
    aid = "0" * 64
    sha = "8" * 64
    _register_asset(db, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid,
        run_id="run_k7",
        source_filename="cand_k7.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.88,
    )
    repo.resolve_candidate(
        cand["candidate_id"],
        {"action": "DISCARD", "reason": "Dibuang pertama kali minimal 10 char"},
        actor="curator-1",
        actor_role="curator",
    )

    with pytest.raises(Conflict):
        repo.resolve_candidate(
            cand["candidate_id"],
            {"action": "DISCARD", "reason": "Dibuang kedua kali minimal 10 char"},
            actor="curator-1",
            actor_role="curator",
        )


def test_k8_set_habitat_moves_and_merges_without_loss(db: Engine):
    """K8: SET_HABITAT moves document from habitat_unknown to resolved habitat without losing media/attributes."""
    repo = DocumentRepository(db)

    # 1. Create document with habitat_unknown
    plant = PlantIdentity(id="plant_k8", label="Cabai Hiyung K8", identity_level="cultivar")
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
            "attr_k8": AttributeValue(
                label="warna",
                value="merah",
                value_type="text",
                resolution="HUMAN_REVIEW",
                current_source=CurrentSourceReference(source_ref="k8.xlsx", sheet="Sheet1", row=2, cell="A2"),
            )
        },
        media_refs=[],
        habitat_unknown=True,
    )
    kms_repo = KmsRepository(db)
    kms_repo.register_source("9" * 64, "cas:///sources/k8.xlsx", 1000, actor="curator-1")
    draft = repo.stage_direct_document(doc_key_src, doc_src, run_id="run_k8_stage", actor="curator-1")
    repo.commit("run_k8_stage", draft["revision"], draft["payload_sha256"], actor="curator-1")

    # 2. Set habitat to real target habitat
    target_hab = HabitatIdentity(
        id="hab_k8_real",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Kalsel", regency_name="Tapin", district_name="Tapin Tengah", village_name="Hiyung"
        ),
        label="Desa Hiyung",
    )

    updated_doc = repo.set_document_habitat(
        doc_key=doc_key_src,
        new_habitat=target_hab,
        actor="curator-1",
        actor_role="curator",
    )

    # Source document must be deleted
    assert repo.get_document(doc_key_src) is None

    # Destination document must exist
    dest_key = f"{plant.id}:{target_hab.id}"
    dest_doc = repo.get_document(dest_key)
    assert dest_doc is not None
    assert dest_doc.get("habitat_unknown") is False
    assert dest_doc["attributes"]["attr_k8"]["value"] == "merah"


def test_k9_candidates_do_not_expire(db: Engine):
    """K9: Candidates persist in DB indefinitely without TTL or auto-expiration."""
    repo = DocumentRepository(db)
    aid = "1" * 64
    sha = "a" * 64
    _register_asset(db, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid,
        run_id="run_k9",
        source_filename="cand_k9.png",
        original_sha256=sha,
        organ_part="buah",
        confidence=0.88,
    )

    # Directly set created_at back by 1 year in DB to simulate old candidate
    with db.begin() as conn:
        conn.execute(
            text("UPDATE kms.image_candidates SET created_at = now() - interval '365 days' WHERE candidate_id = :id"),
            {"id": cand["candidate_id"]},
        )

    candidates = repo.list_candidates(status="CANDIDATE")
    matching = [c for c in candidates if c["candidate_id"] == cand["candidate_id"]]
    assert len(matching) == 1, "Candidate must not expire or be purged"


def test_k10_no_clustering_two_similar_images_create_two_rows(db: Engine):
    """K10: No automatic clustering: two distinct similar images create two individual candidate rows."""
    repo = DocumentRepository(db)
    aid1 = "2" * 64
    aid2 = "3" * 64
    sha1 = "b" * 64
    sha2 = "c" * 64
    _register_asset(db, aid1, sha1)
    _register_asset(db, aid2, sha2)

    c1 = repo.add_candidate(
        asset_id=aid1,
        run_id="run_k10",
        source_filename="similar_01.png",
        original_sha256=sha1,
        organ_part="buah",
        confidence=0.88,
        suggested_name="Cabai Merah Unik",
    )
    c2 = repo.add_candidate(
        asset_id=aid2,
        run_id="run_k10",
        source_filename="similar_02.png",
        original_sha256=sha2,
        organ_part="buah",
        confidence=0.87,
        suggested_name="Cabai Merah Unik",
    )

    assert c1["candidate_id"] != c2["candidate_id"]
    rows = repo.list_candidates(status="CANDIDATE")
    ids = [r["candidate_id"] for r in rows]
    assert c1["candidate_id"] in ids
    assert c2["candidate_id"] in ids


def test_k11_migration_0004_additive_and_checked_by_readyz(db: Engine, tmp_path):
    """K11: Migration 0004 is additive, idempotent, and /readyz checks kms.image_candidates table."""
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    applied = migrate(admin_url)
    # Subsequent call is idempotent
    assert migrate(admin_url) == []

    # Check /readyz on fully migrated db with 0004
    tokens = {"c" * 40: {"subject": "curator-1", "role": "curator"}}
    settings = Settings(
        _env_file=None,
        database_url=os.getenv("TEST_DATABASE_URL"),
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=tmp_path / "media_k11",
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(settings.media_storage_path, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)
    with TestClient(app) as client:
        resp = client.get("/readyz", headers={"Authorization": "Bearer " + "c" * 40})
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}
