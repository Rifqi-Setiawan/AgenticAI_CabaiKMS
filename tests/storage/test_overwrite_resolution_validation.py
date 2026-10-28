"""Unit and integration tests for L2: Server resolution validation in DocumentRepository (R-01..R-07).

Tests:
R-01: REVISE without corrected_unit for an attribute that has an expected unit -> raises InvalidState.
R-02: REVISE with incompatible corrected_unit (e.g. kg vs cm) -> raises InvalidState.
R-03: REVISE with non-numeric corrected_value for number type -> raises InvalidState.
R-04: APPLY_INCOMING without non-empty reason -> raises InvalidState.
R-05: APPLY_INCOMING or REVISE when doc_key or attribute is missing in draft -> raises InvalidState (not silent no-op).
R-06: pydantic ValidationError during attribute validation at commit -> raises InvalidState with attribute_id.
R-07: resolve_review called without actor_role="curator" on protected value -> raises Conflict.
"""

from __future__ import annotations

import copy
import hashlib
import os
import uuid
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import (
    AttributeValue,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


@pytest.fixture
def test_db():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _setup_staged_run(
    engine: Engine,
    run_id: str,
    reviews: list[DocumentReviewItem],
    *,
    resolution: str = "AUTO_ACCEPT",
    attr_id: str = "attr_tinggi_tanaman",
    value_type: str = "number",
    unit: str | None = "cm",
    value: Any = 80.0,
    include_doc: bool = True,
) -> tuple[DocumentRepository, str]:
    kms_repo = KmsRepository(engine)
    doc_repo = DocumentRepository(engine)

    sha = hashlib.sha256(run_id.encode()).hexdigest()
    kms_repo.register_source(sha, f"cas:///sources/{run_id}.xlsx", 1000, actor="curator-1")

    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    plant = PlantIdentity(id="plant_val", label="Cabai Rawit", identity_level="cultivar")
    doc_key = f"{plant.id}:{habitat.id}"

    documents = {}
    if include_doc:
        doc = KnowledgeDocument(
            schema_version="kms-document-v1",
            variety=plant,
            habitat=habitat,
            sampling_locations=[SamplingLocationDetail(location_ref="loc_01", raw_address="Sleman")],
            attributes={
                attr_id: AttributeValue(
                    label="tinggi tanaman",
                    value=value,
                    value_type=value_type,
                    unit=unit,
                    resolution=resolution,
                    current_source=CurrentSourceReference(
                        source_ref="s.xlsx", sheet="S1", row=1, cell="A1", location_ref="loc_01"
                    ),
                )
            },
            media_refs=[],
            updated_by_run=run_id,
            doc_id=doc_key,
        )
        documents[doc_key] = doc

    for r in reviews:
        r.target_document_key = doc_key

    draft = DocumentDraft(
        run_id=run_id,
        source_filename=f"{run_id}.xlsx",
        file_sha256=sha,
        source_uri=f"cas:///sources/{run_id}.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents=documents,
        reviews=reviews,
        base_versions={doc_key: 0} if include_doc else {},
    )
    doc_repo.stage(draft, expected_revision=0, actor="curator-1")
    return doc_repo, doc_key


def test_r01_revise_without_corrected_unit_raises_invalid_state(test_db):
    """R-01: REVISE without corrected_unit for an attribute that has an expected unit -> raises InvalidState."""
    run_id = f"run_r01_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r01",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "UNIT_INCOMPATIBLE",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "kg",
            "old_attribute": {
                "label": "tinggi tanaman",
                "value": 80.0,
                "value_type": "number",
                "unit": "cm",
                "resolution": "AUTO_ACCEPT",
                "current_source": {"source_ref": "s.xlsx", "sheet": "S1", "row": 1, "cell": "A1"},
            },
        },
    )
    repo, _ = _setup_staged_run(test_db, run_id, [rev])

    # REVISE without corrected_unit
    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            run_id,
            "rev_r01",
            {"action": "REVISE", "corrected_value": 85.0, "corrected_unit": None, "reason": "Valid reason min 10 chars"},
            actor="curator-1",
            actor_role="curator",
        )
    assert "corrected_unit" in str(exc.value).lower()


def test_r02_revise_incompatible_unit_raises_invalid_state(test_db):
    """R-02: REVISE with incompatible corrected_unit (e.g. kg vs cm) -> raises InvalidState."""
    run_id = f"run_r02_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r02",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "UNIT_INCOMPATIBLE",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "kg",
            "old_attribute": {
                "label": "tinggi tanaman",
                "value": 80.0,
                "value_type": "number",
                "unit": "cm",
                "resolution": "AUTO_ACCEPT",
                "current_source": {"source_ref": "s.xlsx", "sheet": "S1", "row": 1, "cell": "A1"},
            },
        },
    )
    repo, _ = _setup_staged_run(test_db, run_id, [rev])

    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            run_id,
            "rev_r02",
            {"action": "REVISE", "corrected_value": 85.0, "corrected_unit": "kg", "reason": "Valid reason min 10 chars"},
            actor="curator-1",
            actor_role="curator",
        )
    assert "incompatible" in str(exc.value).lower() or "unit" in str(exc.value).lower()


def test_r03_revise_non_numeric_value_for_number_type_raises_invalid_state(test_db):
    """R-03: REVISE with non-numeric corrected_value for number type -> raises InvalidState."""
    run_id = f"run_r03_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r03",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, "bukan_angka"],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": "bukan_angka",
            "old_unit": "cm",
            "new_unit": None,
            "old_attribute": {
                "label": "tinggi tanaman",
                "value": 80.0,
                "value_type": "number",
                "unit": "cm",
                "resolution": "AUTO_ACCEPT",
                "current_source": {"source_ref": "s.xlsx", "sheet": "S1", "row": 1, "cell": "A1"},
            },
        },
    )
    repo, _ = _setup_staged_run(test_db, run_id, [rev])

    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            run_id,
            "rev_r03",
            {
                "action": "REVISE",
                "corrected_value": "bukan_angka",
                "corrected_unit": "cm",
                "reason": "Valid reason min 10 chars",
            },
            actor="curator-1",
            actor_role="curator",
        )
    assert "number" in str(exc.value).lower() or "numeric" in str(exc.value).lower() or "type" in str(exc.value).lower()


def test_r04_apply_incoming_without_reason_raises_invalid_state(test_db):
    """R-04: APPLY_INCOMING without non-empty reason -> raises InvalidState (for all categories)."""
    run_id = f"run_r04_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r04",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, "tinggi_sekali"],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": "tinggi_sekali",
            "old_unit": "cm",
            "new_unit": None,
        },
    )
    repo, _ = _setup_staged_run(test_db, run_id, [rev])

    # Empty reason or whitespace only
    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            run_id,
            "rev_r04",
            {"action": "APPLY_INCOMING", "reason": "   "},
            actor="curator-1",
            actor_role="curator",
        )
    assert "reason" in str(exc.value).lower()


def test_r05_missing_doc_or_attribute_raises_invalid_state(test_db):
    """R-05: APPLY_INCOMING/REVISE when doc_key or attribute is missing in draft -> raises InvalidState."""
    run_id = f"run_r05_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r05",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, "tinggi_sekali"],
        status="pending",
        payload={
            "attribute_id": "attr_non_existent",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": "tinggi_sekali",
            "old_unit": "cm",
            "new_unit": None,
        },
    )
    # Staged without the document matching target_document_key
    repo, doc_key = _setup_staged_run(test_db, run_id, [rev], include_doc=False)

    with pytest.raises(InvalidState) as exc:
        repo.resolve_review(
            run_id,
            "rev_r05",
            {"action": "APPLY_INCOMING", "reason": "Valid reason min 10 chars"},
            actor="curator-1",
            actor_role="curator",
        )
    assert "not found" in str(exc.value).lower() or "missing" in str(exc.value).lower()


def test_r06_attribute_validation_error_at_commit_raises_invalid_state_with_attr_id(test_db):
    """R-06: Attribute validation error at commit raises InvalidState with attribute_id (not unhandled ValidationError)."""
    run_id = f"run_r06_{uuid.uuid4().hex[:6]}"
    repo, doc_key = _setup_staged_run(test_db, run_id, [])

    # Tamper the staged payload in DB with corrupt attribute data
    with test_db.begin() as conn:
        from src.storage.contracts import canonical_json, digest_json

        run = repo.get_run(run_id)
        payload = copy.deepcopy(run["draft"])
        payload["documents"][doc_key]["attributes"]["attr_corrupt"] = {
            "label": "corrupt attr",
            "value": 123,
            "value_type": "INVALID_TYPE_ENUM",
        }
        sha = digest_json(payload)
        conn.execute(text("SELECT set_config('kms.actor', 'curator-1', true)"))
        conn.execute(
            text("UPDATE kms.acquisition_runs SET draft_payload = :p, payload_sha256 = :s WHERE run_id = :r"),
            {"p": canonical_json(payload), "s": sha, "r": run_id},
        )

    with pytest.raises(InvalidState) as exc:
        repo.commit(run_id, 1, sha, actor="curator-1")
    assert "attr_corrupt" in str(exc.value) or "attribute" in str(exc.value).lower()


def test_r07_resolve_without_curator_role_on_protected_raises_conflict(test_db):
    """R-07: resolve_review called without actor_role="curator" on protected value -> raises Conflict."""
    run_id = f"run_r07_{uuid.uuid4().hex[:6]}"
    rev = DocumentReviewItem(
        item_id="rev_r07",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "EXISTING_HUMAN_PROTECTED",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    repo, _ = _setup_staged_run(test_db, run_id, [rev], resolution="HUMAN_REVIEW")

    # Called with actor_role=None or actor_role="reviewer"
    with pytest.raises(Conflict) as exc:
        repo.resolve_review(
            run_id,
            "rev_r07",
            {"action": "APPLY_INCOMING", "reason": "Valid reason min 10 chars"},
            actor="reviewer-1",
            actor_role="reviewer",
        )
    assert "curator" in str(exc.value).lower()
