"""Tests for Round 4 Storage and Role Security (F-1, F-2, F-3, F-5, F-10).

Executed using least-privilege role 'cabai_app' on test database.
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
from src.storage.migrate import MIGRATIONS, migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def app_role_db(admin_engine: Engine) -> Engine:
    """Fixture providing an Engine connected strictly as the least-privilege 'cabai_app' role."""
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    if not admin_url:
        pytest.skip("TEST_DATABASE_ADMIN_URL not configured")

    # Run migrations using admin url and ensure USAGE on schema kms
    migrate(admin_url)
    with admin_engine.begin() as conn:
        conn.execute(text("GRANT USAGE ON SCHEMA kms TO cabai_app;"))

    # Connect strictly as cabai_app
    app_url = "postgresql+psycopg://cabai_app@/cabai_kms_test?host=/tmp"
    return make_engine(Settings(_env_file=None, database_url=app_url))


@pytest.fixture
def admin_engine() -> Engine:
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", os.getenv("TEST_DATABASE_URL"))
    return make_engine(Settings(_env_file=None, database_url=admin_url))


def _register_asset(admin_engine: Engine, asset_id: str, sha: str):
    repo = KmsRepository(admin_engine)
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


def _stage_and_commit_doc(admin_engine: Engine, doc_key: str, doc: KnowledgeDocument, run_id: str):
    repo = DocumentRepository(admin_engine)
    draft = repo.stage_direct_document(doc_key, doc, run_id=run_id, actor="curator-1")
    repo.commit(run_id, draft["revision"], draft["payload_sha256"], actor="curator-1")


def test_h1_set_habitat_with_cabai_app_role(app_role_db: Engine, admin_engine: Engine):
    """H1: set_document_habitat executes successfully under least-privilege cabai_app role without PermissionDenied."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    # Create habitat_unknown document
    plant = PlantIdentity(id=f"plant_h1_{suffix}", label=f"Cabai H1 {suffix}", identity_level="cultivar")
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
            "attr_warna": AttributeValue(
                label="warna", value="merah", value_type="text", resolution="HUMAN_REVIEW",
                current_source=CurrentSourceReference(source_ref="s.xlsx", sheet="S1", row=2, cell="A2")
            )
        },
        media_refs=[],
        habitat_unknown=True,
    )
    _stage_and_commit_doc(admin_engine, doc_key_src, doc_src, f"run_h1_{suffix}")

    # Set habitat using cabai_app
    target_hab = HabitatIdentity(
        id=f"hab_h1_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="DIY", regency_name="Sleman", district_name="Pakem", village_name="Hargobinangun"
        ),
        label="Desa Hargobinangun",
    )

    # Must succeed without PostgreSQL permission denied on DELETE
    updated = repo.set_document_habitat(
        doc_key=doc_key_src,
        new_habitat=target_hab,
        actor="curator-1",
        actor_role="curator",
    )
    assert updated["habitat"]["id"] == f"hab_h1_{suffix}"
    assert updated.get("habitat_unknown") is False
    assert repo.get_document(doc_key_src) is None


def test_h2_discard_duplicate_sha_idempotent_with_cabai_app_role(app_role_db: Engine, admin_engine: Engine):
    """H2: Multiple DISCARD operations with same sha256 succeed idempotently under cabai_app role."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]
    aid1 = hashlib.sha256(f"aid1_{suffix}".encode()).hexdigest()
    aid2 = hashlib.sha256(f"aid2_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"sha_shared_{suffix}".encode()).hexdigest()

    _register_asset(admin_engine, aid1, sha)
    _register_asset(admin_engine, aid2, sha)

    c1 = repo.add_candidate(
        asset_id=aid1, run_id=f"run_{suffix}", source_filename="f1.png", original_sha256=sha, organ_part="buah", confidence=0.85
    )
    # First discard
    res1 = repo.resolve_candidate(
        c1["candidate_id"],
        {"action": "DISCARD", "reason": "Bukan cabai valid 10 char pertama"},
        actor="curator-1",
        actor_role="curator",
    )
    assert res1["status"] == "DISCARDED"

    # Second candidate with same sha
    with app_role_db.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO kms.image_candidates (candidate_id, asset_id, run_id, source_filename, original_sha256, organ_part, confidence, status, created_at) "
                "VALUES (:cid, :aid, :rid, 'f2.png', :sha, 'buah', 0.85, 'CANDIDATE', now())"
            ),
            {"cid": f"cand_dup_{suffix}", "aid": aid2, "rid": f"run_{suffix}", "sha": sha},
        )

    # Second discard on same sha must NOT fail with permission denied on ON CONFLICT DO UPDATE
    res2 = repo.resolve_candidate(
        f"cand_dup_{suffix}",
        {"action": "DISCARD", "reason": "Bukan cabai valid 10 char kedua"},
        actor="curator-1",
        actor_role="curator",
    )
    assert res2["status"] == "DISCARDED"


def test_g1_promote_on_existing_variety_name_raises_conflict(app_role_db: Engine, admin_engine: Engine):
    """G1: Second PROMOTE with same variety name raises Conflict, first document remains untouched."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]
    aid1 = hashlib.sha256(f"g1_a1_{suffix}".encode()).hexdigest()
    aid2 = hashlib.sha256(f"g1_a2_{suffix}".encode()).hexdigest()
    sha1 = hashlib.sha256(f"g1_s1_{suffix}".encode()).hexdigest()
    sha2 = hashlib.sha256(f"g1_s2_{suffix}".encode()).hexdigest()

    _register_asset(admin_engine, aid1, sha1)
    _register_asset(admin_engine, aid2, sha2)

    c1 = repo.add_candidate(
        asset_id=aid1, run_id=f"run_g1_{suffix}", source_filename="f1.png", original_sha256=sha1, organ_part="buah", confidence=0.88
    )
    c2 = repo.add_candidate(
        asset_id=aid2, run_id=f"run_g1_{suffix}", source_filename="f2.png", original_sha256=sha2, organ_part="daun", confidence=0.87
    )

    var_name = f"Cabai Langka {suffix}"
    # 1. Promote first candidate
    res1 = repo.resolve_candidate(
        c1["candidate_id"],
        {"action": "PROMOTE", "new_variety_name": var_name, "reason": "Varietas baru pertama kali ditemukan"},
        actor="curator-1",
        actor_role="curator",
    )
    assert res1["status"] == "PROMOTED"

    # 2. Promote second candidate with same name -> MUST raise Conflict!
    with pytest.raises(Conflict) as exc:
        repo.resolve_candidate(
            c2["candidate_id"],
            {"action": "PROMOTE", "new_variety_name": var_name, "reason": "Varietas baru kedua harusnya merge"},
            actor="curator-1",
            actor_role="curator",
        )
    assert "already exists" in str(exc.value).lower()
    assert "merge" in str(exc.value).lower()

    # First doc remains with exactly 1 media ref
    norm_id = f"plant_cabai_langka_{suffix}"
    doc = repo.get_document(f"{norm_id}:habitat_unknown")
    assert doc is not None
    assert len(doc["media_refs"]) == 1
    assert doc["media_refs"][0]["asset_id"] == aid1


def test_g2_promote_on_existing_document_with_attributes_raises_conflict(app_role_db: Engine, admin_engine: Engine):
    """G2: PROMOTE on existing document with attributes raises Conflict; attributes preserved."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    # Pre-create document with attributes
    plant = PlantIdentity(id=f"plant_g2_{suffix}", label=f"Cabai G2 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_name="Unknown", regency_name="Unknown", district_name="Unknown", village_name="Unknown"
        ),
        label="Habitat Tidak Diketahui",
    )
    doc_key = f"{plant.id}:{unknown_hab.id}"
    base_doc = KnowledgeDocument(
        variety=plant,
        habitat=unknown_hab,
        attributes={
            "attr_panjang": AttributeValue(
                label="panjang", value=12.5, value_type="number", unit="cm", resolution="HUMAN_REVIEW",
                current_source=CurrentSourceReference(source_ref="s.xlsx", sheet="S1", row=2, cell="A2")
            )
        },
        media_refs=[],
        habitat_unknown=True,
    )
    _stage_and_commit_doc(admin_engine, doc_key, base_doc, f"run_g2_{suffix}")

    aid = hashlib.sha256(f"g2_a_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"g2_s_{suffix}".encode()).hexdigest()
    _register_asset(admin_engine, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid, run_id=f"run_g2_{suffix}", source_filename="f.png", original_sha256=sha, organ_part="buah", confidence=0.89
    )

    with pytest.raises(Conflict):
        repo.resolve_candidate(
            cand["candidate_id"],
            {"action": "PROMOTE", "new_variety_name": f"Cabai G2 {suffix}", "reason": "Mencoba promote menimpa dokumen"},
            actor="curator-1",
            actor_role="curator",
        )

    # Document attributes must remain intact
    doc_after = repo.get_document(doc_key)
    assert doc_after["attributes"]["attr_panjang"]["value"] == 12.5


def test_g3_promote_once_then_merge_twice(app_role_db: Engine, admin_engine: Engine):
    """G3: 3 photos of same new variety: 1 PROMOTE + 2 MERGE produces 1 document with 3 media refs."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]
    var_name = f"Cabai Trio {suffix}"

    aids = [hashlib.sha256(f"g3_a_{i}_{suffix}".encode()).hexdigest() for i in range(3)]
    shas = [hashlib.sha256(f"g3_s_{i}_{suffix}".encode()).hexdigest() for i in range(3)]
    parts = ["buah", "daun", "bunga"]

    cands = []
    for i in range(3):
        _register_asset(admin_engine, aids[i], shas[i])
        c = repo.add_candidate(
            asset_id=aids[i], run_id=f"run_g3_{suffix}", source_filename=f"img_{i}.png", original_sha256=shas[i], organ_part=parts[i], confidence=0.90
        )
        cands.append(c)

    # 1. First photo is PROMOTED
    repo.resolve_candidate(
        cands[0]["candidate_id"],
        {"action": "PROMOTE", "new_variety_name": var_name, "reason": "Foto pertama varietas baru"},
        actor="curator-1",
        actor_role="curator",
    )
    doc_key = f"plant_cabai_trio_{suffix}:habitat_unknown"

    # 2. Second photo is MERGED
    repo.resolve_candidate(
        cands[1]["candidate_id"],
        {"action": "MERGE", "target_doc_key": doc_key, "reason": "Foto kedua daun varietas sama"},
        actor="curator-1",
        actor_role="curator",
    )

    # 3. Third photo is MERGED
    repo.resolve_candidate(
        cands[2]["candidate_id"],
        {"action": "MERGE", "target_doc_key": doc_key, "reason": "Foto ketiga bunga varietas sama"},
        actor="curator-1",
        actor_role="curator",
    )

    final_doc = repo.get_document(doc_key)
    assert len(final_doc["media_refs"]) == 3
    media_parts = {m["organ_part"] for m in final_doc["media_refs"]}
    assert media_parts == {"buah", "daun", "bunga"}


def test_i1_set_habitat_target_same_as_source_raises_invalid_state(app_role_db: Engine, admin_engine: Engine):
    """I1: Destination habitat producing same doc_key raises InvalidState; doc untouched."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    plant = PlantIdentity(id=f"plant_i1_{suffix}", label=f"Cabai I1 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="U", regency_name="U", district_name="U", village_name="U"),
        label="Habitat Tidak Diketahui",
    )
    doc_key = f"{plant.id}:{unknown_hab.id}"
    doc = KnowledgeDocument(
        variety=plant, habitat=unknown_hab, attributes={}, media_refs=[], habitat_unknown=True
    )
    _stage_and_commit_doc(admin_engine, doc_key, doc, f"run_i1_{suffix}")

    with pytest.raises(InvalidState) as exc:
        repo.set_document_habitat(
            doc_key=doc_key,
            new_habitat=unknown_hab,  # target == source!
            actor="curator-1",
            actor_role="curator",
        )
    assert repo.get_document(doc_key) is not None


def test_i2_set_habitat_target_unknown_raises_invalid_state(app_role_db: Engine, admin_engine: Engine):
    """I2: Destination habitat being habitat_unknown raises InvalidState."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]
    plant = PlantIdentity(id=f"plant_i2_{suffix}", label=f"Cabai I2 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="U", regency_name="U", district_name="U", village_name="U"),
        label="Habitat Tidak Diketahui",
    )
    doc_key = f"{plant.id}:{unknown_hab.id}"
    doc = KnowledgeDocument(variety=plant, habitat=unknown_hab, attributes={}, media_refs=[], habitat_unknown=True)
    _stage_and_commit_doc(admin_engine, doc_key, doc, f"run_i2_{suffix}")

    with pytest.raises(InvalidState):
        repo.set_document_habitat(
            doc_key=doc_key,
            new_habitat={"id": "habitat_unknown", "label": "Unknown"},
            actor="curator-1",
            actor_role="curator",
        )


def test_i3_set_habitat_on_non_unknown_source_raises_invalid_state(app_role_db: Engine, admin_engine: Engine):
    """I3: Attempting set_document_habitat on already resolved source document raises InvalidState."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    plant = PlantIdentity(id=f"plant_i3_{suffix}", label=f"Cabai I3 {suffix}", identity_level="cultivar")
    hab_real = HabitatIdentity(
        id=f"hab_real_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Jabar", regency_name="Garut", district_name="Tarogong", village_name="Pananjung"),
        label="Desa Pananjung",
    )
    doc_key = f"{plant.id}:{hab_real.id}"
    doc = KnowledgeDocument(variety=plant, habitat=hab_real, attributes={}, media_refs=[], habitat_unknown=False)
    _stage_and_commit_doc(admin_engine, doc_key, doc, f"run_i3_{suffix}")

    new_hab = HabitatIdentity(
        id=f"hab_new_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Jabar", regency_name="Bandung", district_name="Coblong", village_name="Dago"),
        label="Kelurahan Dago",
    )
    with pytest.raises(InvalidState):
        repo.set_document_habitat(doc_key=doc_key, new_habitat=new_hab, actor="curator-1", actor_role="curator")


def test_i4_set_habitat_attribute_conflict_raises_conflict(app_role_db: Engine, admin_engine: Engine):
    """I4: Merge into existing destination doc with conflicting attribute value raises Conflict (no silent loss)."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    plant = PlantIdentity(id=f"plant_i4_{suffix}", label=f"Cabai I4 {suffix}", identity_level="cultivar")
    unknown_hab = HabitatIdentity(
        id="habitat_unknown",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="U", regency_name="U", district_name="U", village_name="U"),
        label="Habitat Tidak Diketahui",
    )
    dest_hab = HabitatIdentity(
        id=f"hab_dest_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="DIY", regency_name="Sleman", district_name="Pakem", village_name="Hargobinangun"),
        label="Desa Hargobinangun",
    )

    # Source doc has attribute 'tinggi' = 70.0
    doc_src = KnowledgeDocument(
        variety=plant, habitat=unknown_hab,
        attributes={"attr_tinggi": AttributeValue(label="tinggi", value=70.0, value_type="number", unit="cm", resolution="HUMAN_REVIEW", current_source=CurrentSourceReference(source_ref="s1.xlsx", sheet="S1", row=2, cell="A2"))},
        media_refs=[], habitat_unknown=True
    )
    _stage_and_commit_doc(admin_engine, f"{plant.id}:{unknown_hab.id}", doc_src, f"run_i4_s_{suffix}")

    # Dest doc already exists with attribute 'tinggi' = 85.0 (CONFLICT!)
    doc_dest = KnowledgeDocument(
        variety=plant, habitat=dest_hab,
        attributes={"attr_tinggi": AttributeValue(label="tinggi", value=85.0, value_type="number", unit="cm", resolution="HUMAN_REVIEW", current_source=CurrentSourceReference(source_ref="s2.xlsx", sheet="S1", row=2, cell="A2"))},
        media_refs=[], habitat_unknown=False
    )
    _stage_and_commit_doc(admin_engine, f"{plant.id}:{dest_hab.id}", doc_dest, f"run_i4_d_{suffix}")

    with pytest.raises(Conflict) as exc:
        repo.set_document_habitat(
            doc_key=f"{plant.id}:{unknown_hab.id}",
            new_habitat=dest_hab,
            actor="curator-1",
            actor_role="curator",
        )
    assert "conflict" in str(exc.value).lower()
    # Source document must still exist!
    assert repo.get_document(f"{plant.id}:{unknown_hab.id}") is not None


def test_j1_promote_with_non_existent_habitat_id_raises_invalid_state(app_role_db: Engine, admin_engine: Engine):
    """J1: PROMOTE with non-existent habitat_id raises InvalidState (no fabricated habitat)."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]
    aid = hashlib.sha256(f"j1_a_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"j1_s_{suffix}".encode()).hexdigest()
    _register_asset(admin_engine, aid, sha)

    cand = repo.add_candidate(
        asset_id=aid, run_id=f"run_j1_{suffix}", source_filename="f.png", original_sha256=sha, organ_part="buah", confidence=0.88
    )

    with pytest.raises(InvalidState) as exc:
        repo.resolve_candidate(
            cand["candidate_id"],
            {
                "action": "PROMOTE",
                "new_variety_name": f"Cabai J1 {suffix}",
                "habitat_id": "hab_khayalan_tidak_ada",
                "reason": "Mencoba promote habitat palsu minimal 10 char",
            },
            actor="curator-1",
            actor_role="curator",
        )
    assert "not found" in str(exc.value).lower()


def test_j2_promote_with_valid_existing_habitat_id_uses_real_habitat(app_role_db: Engine, admin_engine: Engine):
    """J2: PROMOTE with valid existing habitat_id resolves to authentic HabitatIdentity."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    # Pre-create a document with an authentic habitat
    real_hab = HabitatIdentity(
        id=f"hab_authentic_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="Jatim", regency_name="Malang", district_name="Pujon", village_name="Pandansari"),
        label="Desa Pandansari",
    )
    plant_ref = PlantIdentity(id=f"plant_ref_{suffix}", label=f"Cabai Ref {suffix}", identity_level="cultivar")
    doc_ref = KnowledgeDocument(variety=plant_ref, habitat=real_hab, attributes={}, media_refs=[])
    _stage_and_commit_doc(admin_engine, f"{plant_ref.id}:{real_hab.id}", doc_ref, f"run_ref_{suffix}")

    # Now promote candidate targeting that real habitat_id
    aid = hashlib.sha256(f"j2_a_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"j2_s_{suffix}".encode()).hexdigest()
    _register_asset(app_role_db, aid, sha)
    cand = repo.add_candidate(
        asset_id=aid, run_id=f"run_j2_{suffix}", source_filename="f.png", original_sha256=sha, organ_part="buah", confidence=0.90
    )

    resolved = repo.resolve_candidate(
        cand["candidate_id"],
        {
            "action": "PROMOTE",
            "new_variety_name": f"Cabai Pandansari {suffix}",
            "habitat_id": f"hab_authentic_{suffix}",
            "reason": "Ditemukan di Desa Pandansari Malang yang sudah terdaftar",
        },
        actor="curator-1",
        actor_role="curator",
    )
    assert resolved["status"] == "PROMOTED"

    new_doc_key = f"plant_cabai_pandansari_{suffix}:{real_hab.id}"
    new_doc = repo.get_document(new_doc_key)
    assert new_doc is not None
    assert new_doc["habitat"]["id"] == f"hab_authentic_{suffix}"
    assert new_doc["habitat"]["administrative_path"]["village_name"] == "Pandansari"
    assert new_doc.get("habitat_unknown") is False


def test_o1_merge_with_expected_version_mismatch_raises_conflict(app_role_db: Engine, admin_engine: Engine):
    """O1: MERGE with expected_version mismatch raises Conflict (concurrency protection)."""
    repo = DocumentRepository(app_role_db)
    suffix = uuid.uuid4().hex[:8]

    plant = PlantIdentity(id=f"plant_o1_{suffix}", label=f"Cabai O1 {suffix}", identity_level="cultivar")
    hab = HabitatIdentity(
        id=f"hab_o1_{suffix}",
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(province_name="U", regency_name="U", district_name="U", village_name="U"),
        label="Desa O1",
    )
    doc_key = f"{plant.id}:{hab.id}"
    doc = KnowledgeDocument(variety=plant, habitat=hab, attributes={}, media_refs=[])
    _stage_and_commit_doc(admin_engine, doc_key, doc, f"run_o1_{suffix}")

    aid = hashlib.sha256(f"o1_a_{suffix}".encode()).hexdigest()
    sha = hashlib.sha256(f"o1_s_{suffix}".encode()).hexdigest()
    _register_asset(admin_engine, aid, sha)
    cand = repo.add_candidate(
        asset_id=aid, run_id=f"run_o1_{suffix}", source_filename="f.png", original_sha256=sha, organ_part="buah", confidence=0.88
    )

    with pytest.raises(Conflict) as exc:
        repo.resolve_candidate(
            cand["candidate_id"],
            {
                "action": "MERGE",
                "target_doc_key": doc_key,
                "expected_version": 99,  # Mismatch! Current is 1
                "reason": "Mencoba merge dengan versi kadaluwarsa",
            },
            actor="curator-1",
            actor_role="curator",
        )
    assert "version mismatch" in str(exc.value).lower()
