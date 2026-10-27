"""Integration tests for L3: Overwrite review resolution in DocumentRepository (T-13..T-20).

Tests:
T-13: KEEP_EXISTING -> review rejected, document value intact, commit succeeds, 0 rows in ledger.
T-14: APPLY_INCOMING on OVERWRITE_BLOCKED -> new value applied with resolution HUMAN_REVIEW,
      commit succeeds, 1 row in document_attribute_changes ledger.
T-15: UNIT_MISMATCH + APPLY_INCOMING without correction -> InvalidState.
T-16: UNIT_MISMATCH + REVISE with compatible correction -> revised, corrected value/unit applied.
T-17: Unknown action -> InvalidState, item remains pending.
T-18: Commit before resolving review item -> Conflict.
T-19: Resolve twice -> Conflict.
T-20: Overwriting EXISTING_HUMAN_PROTECTED: non-curator rejected; curator without reason rejected;
      curator with reason accepted.
"""

from __future__ import annotations

import copy
import os
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.storage.attribute_policy import AttributePolicy
from src.storage.config import Settings
from src.storage.db import make_engine
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
from src.storage.errors import Conflict, InvalidState
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.migrate import migrate

pytestmark = pytest.mark.integration


@pytest.fixture
def db() -> Engine:
    """Provide a real PostgreSQL database with all migrations applied."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; PostgreSQL test database required.")

    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _build_plant(plant_id: str, label: str) -> PlantIdentity:
    return PlantIdentity(id=plant_id, label=label, identity_level="cultivar")


def _build_habitat(hab_id: str) -> HabitatIdentity:
    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    return habitat


def _build_attr(
    label: str,
    value: any,
    value_type: str = "number",
    unit: str | None = "cm",
    resolution: str = "AUTO_ACCEPT",
) -> AttributeValue:
    return AttributeValue(
        label=label,
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        unit=unit,
        resolution=resolution,  # type: ignore[arg-type]
        mapping_policy_version="exact-alias-policy-v1",
        current_source=CurrentSourceReference(
            source_ref="survey_test.xlsx",
            sheet="Resume Data",
            row=2,
            cell="B2",
            location_ref="loc_001",
        ),
    )


def _setup_existing_doc(repo: DocumentRepository, plant: PlantIdentity, habitat: HabitatIdentity, resolution: str = "AUTO_ACCEPT"):
    sha = "a" * 64
    repo.register_source(sha, "cas:///sources/init.xlsx", 1000, actor="test-curator")
    doc_key = f"{plant.id}:{habitat.id}"
    init_attr = _build_attr("tinggi tanaman", 80.0, "number", "cm", resolution=resolution)
    doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[
            SamplingLocationDetail(
                location_ref="loc_001",
                raw_address="Dusun Karang, Desa Hargobinangun, Sleman",
                hamlet="Dusun Karang",
            )
        ],
        attributes={"attr_tinggi_tanaman": init_attr},
        media_refs=[],
        updated_by_run="run_init",
    )
    draft = DocumentDraft(
        run_id="run_init",
        source_filename="init.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/init.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc},
        reviews=[],
        base_versions={doc_key: 0},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")
    repo.commit("run_init", staged["revision"], staged["payload_sha256"], actor="test-curator")


def test_t13_keep_existing_rejects_review_and_preserves_old(db: Engine):
    """T-13: KEEP_EXISTING -> review rejected, doc value intact, commit succeeds, 0 ledger rows."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_13", "Cabai Rawit")
    habitat = _build_habitat("hab_13")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    # Second run plans incoming type mismatch -> OVERWRITE_BLOCKED
    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "sangat tinggi",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t13")
    assert len(draft.reviews) == 1
    rev_id = draft.reviews[0].item_id

    sha = "b" * 64
    repo.register_source(sha, "cas:///sources/t13.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t13.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}

    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    # Resolve review with KEEP_EXISTING
    resolved = repo.resolve_review(
        "run_t13",
        rev_id,
        {"action": "KEEP_EXISTING", "notes": "Keep old measurement"},
        actor="curator-1",
        actor_role="curator",
    )
    assert resolved["status"] == "rejected"

    # Commit succeeds
    run = repo.get_run("run_t13")
    receipt = repo.commit("run_t13", run["revision"], run["payload_sha256"], actor="curator-1")
    assert receipt is not None

    # Verify doc value intact (80.0)
    updated_doc = repo.get_document(doc_key)
    assert updated_doc.attributes["attr_tinggi_tanaman"].value == 80.0

    # 0 rows in ledger
    with db.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM kms.document_attribute_changes WHERE run_id = 'run_t13'")
        ).scalar()
    assert count == 0


def test_t14_apply_incoming_updates_draft_and_writes_ledger(db: Engine):
    """T-14: APPLY_INCOMING on OVERWRITE_BLOCKED -> new value applied, HUMAN_REVIEW resolution, commit logs ledger."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_14", "Cabai Rawit")
    habitat = _build_habitat("hab_14")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    # Second run plans incoming type mismatch -> OVERWRITE_BLOCKED
    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "tinggi_moderat",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t14")
    rev_id = draft.reviews[0].item_id

    sha = "c" * 64
    repo.register_source(sha, "cas:///sources/t14.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t14.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}

    repo.stage(draft, expected_revision=0, actor="test-curator")

    # Resolve with APPLY_INCOMING
    resolved = repo.resolve_review(
        "run_t14",
        rev_id,
        {"action": "APPLY_INCOMING", "reason": "Approved qualitative update", "notes": "Approved"},
        actor="curator-1",
        actor_role="curator",
    )
    assert resolved["status"] == "approved"

    # Commit succeeds
    run = repo.get_run("run_t14")
    repo.commit("run_t14", run["revision"], run["payload_sha256"], actor="curator-1")

    # Verify doc has new value and resolution HUMAN_REVIEW
    updated_doc = repo.get_document(doc_key)
    attr = updated_doc.attributes["attr_tinggi_tanaman"]
    assert attr.value == "tinggi_moderat"
    assert attr.resolution == "HUMAN_REVIEW"

    # Exactly 1 row in ledger
    with db.connect() as conn:
        changes = conn.execute(
            text("SELECT old_value, new_value, actor FROM kms.document_attribute_changes WHERE run_id = 'run_t14'")
        ).mappings().all()
    assert len(changes) == 1
    assert changes[0]["old_value"]["value"] == 80.0
    assert changes[0]["new_value"]["value"] == "tinggi_moderat"
    assert changes[0]["actor"] == "curator-1"


def test_t15_unit_mismatch_apply_incoming_without_correction_raises_invalid_state(db: Engine):
    """T-15: UNIT_MISMATCH + APPLY_INCOMING without correction raises InvalidState."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_15", "Cabai Rawit")
    habitat = _build_habitat("hab_15")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "85.0 kg",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t15")
    assert draft.reviews[0].category == "UNIT_MISMATCH"
    rev_id = draft.reviews[0].item_id

    sha = "d" * 64
    repo.register_source(sha, "cas:///sources/t15.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t15.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    repo.stage(draft, expected_revision=0, actor="test-curator")

    # Cannot blindly APPLY_INCOMING an incompatible unit!
    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            "run_t15",
            rev_id,
            {"action": "APPLY_INCOMING"},
            actor="curator-1",
            actor_role="curator",
        )
    assert "unit" in str(exc.value).lower()


def test_t16_unit_mismatch_revise_applies_compatible_correction(db: Engine):
    """T-16: UNIT_MISMATCH + REVISE with compatible correction -> revised, corrected value/unit applied."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_16", "Cabai Rawit")
    habitat = _build_habitat("hab_16")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "85.0 kg",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t16")
    rev_id = draft.reviews[0].item_id

    sha = "e" * 64
    repo.register_source(sha, "cas:///sources/t16.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t16.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    repo.stage(draft, expected_revision=0, actor="test-curator")

    # Revise with corrected value 85.0 and unit cm
    resolved = repo.resolve_review(
        "run_t16",
        rev_id,
        {
            "action": "REVISE",
            "corrected_value": 85.0,
            "corrected_unit": "cm",
            "reason": "Corrected typo in source unit (kg -> cm)",
        },
        actor="curator-1",
        actor_role="curator",
    )
    assert resolved["status"] == "revised"

    # Commit succeeds
    run = repo.get_run("run_t16")
    repo.commit("run_t16", run["revision"], run["payload_sha256"], actor="curator-1")

    updated_doc = repo.get_document(doc_key)
    attr = updated_doc.attributes["attr_tinggi_tanaman"]
    assert attr.value == 85.0
    assert attr.unit == "cm"
    assert attr.resolution == "HUMAN_REVIEW"


def test_t17_unknown_action_raises_invalid_state(db: Engine):
    """T-17: Unknown review resolution action raises InvalidState and item stays pending."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_17", "Cabai Rawit")
    habitat = _build_habitat("hab_17")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "85.0 kg",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t17")
    rev_id = draft.reviews[0].item_id

    sha = "f" * 64
    repo.register_source(sha, "cas:///sources/t17.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t17.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    repo.stage(draft, expected_revision=0, actor="test-curator")

    with pytest.raises(InvalidState):
        repo.resolve_review(
            "run_t17",
            rev_id,
            {"action": "SOME_UNKNOWN_ACTION"},
            actor="curator-1",
            actor_role="curator",
        )

    # Item stays pending
    run = repo.get_run("run_t17")
    r_item = next(r for r in run["draft_payload"]["reviews"] if r["item_id"] == rev_id)
    assert r_item["status"] == "pending"


def test_t18_commit_before_resolved_raises_conflict(db: Engine):
    """T-18: Committing draft before resolving pending overwrite review item raises Conflict."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_18", "Cabai Rawit")
    habitat = _build_habitat("hab_18")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "85.0 kg",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t18")

    sha = "1" * 64
    repo.register_source(sha, "cas:///sources/t18.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t18.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    # Attempt commit without resolving review
    with pytest.raises(Conflict):
        repo.commit("run_t18", staged["revision"], staged["payload_sha256"], actor="test-curator")


def test_t19_resolve_twice_raises_conflict(db: Engine):
    """T-19: Resolving an already-resolved review item raises Conflict."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_19", "Cabai Rawit")
    habitat = _build_habitat("hab_19")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat)

    planner = DocumentPlanner()
    records = [{
        "_row": 2,
        "_sheet": "Resume Data",
        "Varietas": "Cabai Rawit",
        "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
        "tinggi tanaman": "tinggi_sekali",
    }]
    raw_doc = repo.get_document(doc_key)
    if isinstance(raw_doc, dict):
        clean_doc = copy.deepcopy(raw_doc)
        clean_doc.pop("id", None)
        base_doc = KnowledgeDocument.model_validate(clean_doc)
    else:
        base_doc = raw_doc
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t19")
    rev_id = draft.reviews[0].item_id

    sha = "2" * 64
    repo.register_source(sha, "cas:///sources/t19.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t19.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    repo.stage(draft, expected_revision=0, actor="test-curator")

    repo.resolve_review("run_t19", rev_id, {"action": "KEEP_EXISTING"}, actor="curator-1", actor_role="curator")

    with pytest.raises(Conflict):
        repo.resolve_review("run_t19", rev_id, {"action": "KEEP_EXISTING"}, actor="curator-1", actor_role="curator")


def test_t20_overwriting_human_protected_requires_curator_and_reason(db: Engine):
    """T-20: Overwriting EXISTING_HUMAN_PROTECTED: non-curator rejected, curator without reason rejected, curator with reason accepted."""
    repo = DocumentRepository(db)
    plant = _build_plant("plant_rawit_20", "Cabai Rawit")
    habitat = _build_habitat("hab_20")
    doc_key = f"{plant.id}:{habitat.id}"
    _setup_existing_doc(repo, plant, habitat, resolution="HUMAN_REVIEW")

    # Plan incoming measurement -> OVERWRITE_BLOCKED with reason_code EXISTING_HUMAN_PROTECTED
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
    draft = planner.plan_records(records, current_documents={doc_key: base_doc}, run_id="run_t20")
    assert draft.reviews[0].payload.get("reason_code") == "EXISTING_HUMAN_PROTECTED"
    rev_id = draft.reviews[0].item_id

    sha = "3" * 64
    repo.register_source(sha, "cas:///sources/t20.xlsx", 1000, actor="test-curator")
    draft.source_uri = "cas:///sources/t20.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {doc_key: 1}
    repo.stage(draft, expected_revision=0, actor="test-curator")

    # 1. Non-curator (reviewer) rejected
    with pytest.raises(Conflict):
        repo.resolve_review(
            "run_t20",
            rev_id,
            {"action": "APPLY_INCOMING", "reason": "Try overwrite"},
            actor="reviewer-1",
            actor_role="reviewer",
        )

    # 2. Curator without reason rejected
    with pytest.raises(InvalidState):
        repo.resolve_review(
            "run_t20",
            rev_id,
            {"action": "APPLY_INCOMING", "reason": ""},
            actor="curator-1",
            actor_role="curator",
        )

    # 3. Curator with reason accepted
    resolved = repo.resolve_review(
        "run_t20",
        rev_id,
        {"action": "APPLY_INCOMING", "reason": "Verified field re-survey with senior agronomist"},
        actor="curator-1",
        actor_role="curator",
    )
    assert resolved["status"] == "approved"
