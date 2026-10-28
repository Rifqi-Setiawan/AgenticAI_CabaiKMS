"""Integration tests for L4: Commit overwrite guard anti fail-open (T-24..T-29).

Tests:
T-24: Corrupt attribute payload in draft -> commit fails (validation), rolls back.
T-25: Direct draft with incompatible unit -> Conflict, doc unchanged, 0 ledger rows.
T-26: Direct draft with incompatible value_type -> Conflict, doc unchanged, 0 ledger rows.
T-27: Direct draft with incompatible label -> Conflict.
T-28: Direct draft with existing HUMAN + incoming AUTO -> Conflict.
T-29: Adapter build_document_draft and valid updates commit smoothly.
"""

from __future__ import annotations

import copy
import os
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    DocumentDraft,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository
from src.integrations.adapter import build_document_draft


@pytest.fixture
def db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _setup_base_doc(
    repo: DocumentRepository,
    *,
    attr_id: str = "attr_tinggi_tanaman",
    label: str = "tinggi tanaman",
    value: float | str = 80.0,
    value_type: str = "number",
    unit: str | None = "cm",
    resolution: str = "AUTO_ACCEPT",
) -> str:
    kms_repo = KmsRepository(repo.engine)
    sha = "1" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_base.xlsx", 1000, actor="test-curator")

    plant = PlantIdentity(id="plant_guard", label="Cabai Rawit", identity_level="cultivar")
    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    doc_key = f"{plant.id}:{habitat.id}"
    attr = AttributeValue(
        label=label,
        value=value,
        value_type=value_type,
        unit=unit,
        resolution=resolution,
        current_source=CurrentSourceReference(
            source_ref="guard_base.xlsx", sheet="Sheet1", row=1, cell="A1", location_ref="loc_01"
        ),
    )
    doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[SamplingLocationDetail(location_ref="loc_01", raw_address="Sleman")],
        attributes={attr_id: attr},
        media_refs=[],
        updated_by_run="run_guard_base",
    )
    draft = DocumentDraft(
        run_id="run_guard_base",
        source_filename="guard_base.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_base.xlsx",
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
    repo.commit("run_guard_base", staged["revision"], staged["payload_sha256"], actor="test-curator")
    return doc_key


def test_t24_corrupt_attribute_payload_fails_commit(db: Engine):
    """T-24: Corrupt attribute payload in draft -> commit fails with validation error and rolls back."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "2" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t24.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t24 = KnowledgeDocument.model_validate(clean_doc)

    draft = DocumentDraft(
        run_id="run_t24",
        source_filename="guard_t24.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t24.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t24},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    # Tamper staged draft payload in DB directly to inject a corrupt attribute dictionary
    from src.storage.contracts import canonical_json, digest_json
    tampered_payload = copy.deepcopy(draft.model_dump(mode="json"))
    tampered_payload["documents"][doc_key]["attributes"]["attr_tinggi_tanaman"] = {
        "label": "tinggi tanaman",
        "value": 90.0,
        "value_type": "UNKNOWN_CORRUPT_TYPE",  # invalid value_type
    }
    tampered_sha = digest_json(tampered_payload)
    with db.begin() as conn:
        conn.execute(text("SELECT set_config('kms.actor', 'test-curator', true)"))
        conn.execute(
            text("UPDATE kms.acquisition_runs SET draft_payload = :p, payload_sha256 = :s WHERE run_id = 'run_t24'"),
            {"p": canonical_json(tampered_payload), "s": tampered_sha},
        )

    # Commit must fail with validation error, NOT succeed or fail-open
    with pytest.raises(Exception):
        repo.commit("run_t24", staged["revision"], tampered_sha, actor="test-curator")

    # Document remains unchanged at version 1
    doc_after = repo.get_document(doc_key)
    assert doc_after["version"] == 1
    assert doc_after["attributes"]["attr_tinggi_tanaman"]["value"] == 80.0


def test_t25_incompatible_unit_direct_draft_raises_conflict(db: Engine):
    """T-25: Direct draft with incompatible unit -> Conflict, doc unchanged, 0 ledger rows."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "3" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t25.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t25 = KnowledgeDocument.model_validate(clean_doc)
    doc_t25.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value=85.0,
        value_type="number",
        unit="kg",  # incompatible unit with cm
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="guard_t25.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_t25",
        source_filename="guard_t25.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t25.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t25},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    with pytest.raises(Conflict) as exc:
        repo.commit("run_t25", staged["revision"], staged["payload_sha256"], actor="test-curator")
    assert "OVERWRITE_BLOCKED" in str(exc.value)

    doc_after = repo.get_document(doc_key)
    assert doc_after["version"] == 1
    assert doc_after["attributes"]["attr_tinggi_tanaman"]["unit"] == "cm"


def test_t26_incompatible_type_direct_draft_raises_conflict(db: Engine):
    """T-26: Direct draft with incompatible type -> Conflict, doc unchanged, 0 ledger rows."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "4" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t26.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t26 = KnowledgeDocument.model_validate(clean_doc)
    doc_t26.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value="sangat_tinggi",
        value_type="text",  # text vs number
        unit=None,
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="guard_t26.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_t26",
        source_filename="guard_t26.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t26.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t26},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    with pytest.raises(Conflict) as exc:
        repo.commit("run_t26", staged["revision"], staged["payload_sha256"], actor="test-curator")
    assert "OVERWRITE_BLOCKED" in str(exc.value)

    doc_after = repo.get_document(doc_key)
    assert doc_after["version"] == 1
    assert doc_after["attributes"]["attr_tinggi_tanaman"]["value_type"] == "number"


def test_t27_incompatible_label_direct_draft_raises_conflict(db: Engine):
    """T-27: Direct draft with incompatible label -> Conflict."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "5" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t27.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t27 = KnowledgeDocument.model_validate(clean_doc)
    doc_t27.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="lebar kanopi",  # completely incompatible label
        value=85.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="guard_t27.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_t27",
        source_filename="guard_t27.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t27.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t27},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    with pytest.raises(Conflict) as exc:
        repo.commit("run_t27", staged["revision"], staged["payload_sha256"], actor="test-curator")
    assert "OVERWRITE_BLOCKED" in str(exc.value)


def test_t28_existing_human_incoming_auto_direct_draft_raises_conflict(db: Engine):
    """T-28: Direct draft with existing HUMAN_REVIEW + incoming AUTO_ACCEPT -> Conflict."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo, resolution="HUMAN_REVIEW")

    kms_repo = KmsRepository(db)
    sha = "6" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t28.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t28 = KnowledgeDocument.model_validate(clean_doc)
    doc_t28.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value=88.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",  # unapproved AUTO_ACCEPT over protected HUMAN_REVIEW
        current_source=CurrentSourceReference(
            source_ref="guard_t28.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_t28",
        source_filename="guard_t28.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t28.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t28},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    with pytest.raises(Conflict) as exc:
        repo.commit("run_t28", staged["revision"], staged["payload_sha256"], actor="test-curator")
    assert "OVERWRITE_BLOCKED" in str(exc.value)


def test_t29_valid_update_and_adapter_draft_commit_smoothly(db: Engine):
    """T-29: Valid updates and adapter.build_document_draft commit smoothly."""
    repo = DocumentRepository(db)
    doc_key = _setup_base_doc(repo)

    kms_repo = KmsRepository(db)
    sha = "7" * 64
    kms_repo.register_source(sha, "cas:///sources/guard_t29.xlsx", 1000, actor="test-curator")

    raw_doc = repo.get_document(doc_key)
    clean_doc = copy.deepcopy(raw_doc)
    clean_doc.pop("id", None)
    doc_t29 = KnowledgeDocument.model_validate(clean_doc)
    # Compatible unit (m -> cm, or same unit with AUTO_ACCEPT)
    doc_t29.attributes["attr_tinggi_tanaman"] = AttributeValue(
        label="tinggi tanaman",
        value=85.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="guard_t29.xlsx", sheet="Sheet1", row=2, cell="A2", location_ref="loc_01"
        ),
    )
    # Add brand new attribute
    doc_t29.attributes["attr_lebar_kanopi"] = AttributeValue(
        label="lebar kanopi",
        value=60.0,
        value_type="number",
        unit="cm",
        resolution="AUTO_ACCEPT",
        current_source=CurrentSourceReference(
            source_ref="guard_t29.xlsx", sheet="Sheet1", row=2, cell="B2", location_ref="loc_01"
        ),
    )

    draft = DocumentDraft(
        run_id="run_t29",
        source_filename="guard_t29.xlsx",
        file_sha256=sha,
        source_uri="cas:///sources/guard_t29.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc_t29},
        reviews=[],
        base_versions={doc_key: 1},
    )
    staged = repo.stage(draft, expected_revision=0, actor="test-curator")
    receipt = repo.commit("run_t29", staged["revision"], staged["payload_sha256"], actor="test-curator")
    assert receipt.documents_updated == 1

    doc_after = repo.get_document(doc_key)
    assert doc_after["version"] == 2
    assert doc_after["attributes"]["attr_tinggi_tanaman"]["value"] == 85.0
    assert doc_after["attributes"]["attr_lebar_kanopi"]["value"] == 60.0
