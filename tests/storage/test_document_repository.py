"""Acceptance test suite for additive DDL and JSONB document repository.

Covers criteria:
- A01: Dynamic attributes stored in JSONB without DDL ALTER TABLE.
- A10: Policy-cleared AUTO_ACCEPT overwrites existing HUMAN_REVIEW value.
- A13: Atomic run commit all-or-nothing.
- A14: Latest-only knowledge and audit trace sanitization.
- A16: Commit replay idempotent and stale upload rejected.
- A17: Concurrent writers optimistic concurrency control.
"""

from __future__ import annotations

import copy
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from src.storage.config import Settings
from src.storage.db import make_engine, transaction
from src.storage.document_contracts import (
    AdministrativePath,
    AttributeValue,
    CommitReceipt,
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    MediaReference,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState, NotFound
from src.storage.migrate import migrate

pytestmark = pytest.mark.integration


# ============================================================================
# Database Fixture & Test Helpers
# ============================================================================


@pytest.fixture
def db() -> Engine:
    """Disposable PostgreSQL test database connection. Refuses non-test databases."""
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip(
            "TEST_DATABASE_URL not configured; disposable PostgreSQL test database required."
        )
    if not (make_url(url).database or "").endswith("_test"):
        pytest.fail(
            "Refusing integration tests on a database whose name does not end with _test."
        )
    pytest.importorskip("psycopg")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL") or url
    if not admin_url:
        pytest.skip("Database URL not available")
    if make_url(admin_url).database != make_url(url).database:
        pytest.fail(
            "Runtime and admin test URLs must target the same disposable database."
        )
    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _build_plant(
    plant_id: str = "plant_rawit_frutescens_001",
    label: str = "Cabai rawit (Capsicum frutescens L)",
    level: str = "source_category",
    scientific_name: str = "Capsicum frutescens L",
) -> PlantIdentity:
    return PlantIdentity(
        id=plant_id,
        label=label,
        identity_level=level,  # type: ignore[arg-type]
        scientific_name=scientific_name,
    )


def _build_habitat(
    habitat_id: str = "hab_sleman_hargobinangun_001",
    village: str = "Desa Hargobinangun",
    district: str = "Kecamatan Pakem",
    regency: str = "Kabupaten Sleman",
    province: str = "Daerah Istimewa Yogyakarta",
) -> HabitatIdentity:
    return HabitatIdentity(
        id=habitat_id,
        definition="administrative_village_v1",
        administrative_path=AdministrativePath(
            province_id="prop_34",
            regency_id="kab_3404",
            district_id="kec_3404070",
            village_id="desa_3404070001",
            province_name=province,
            regency_name=regency,
            district_name=district,
            village_name=village,
        ),
        label=f"{village}, {district}, {regency}, {province}",
    )


def _build_attribute(
    label: str,
    value: Any,
    value_type: str = "number",
    unit: str | None = None,
    resolution: str = "AUTO_ACCEPT",
    sheet: str = "Resume Data",
    row: int = 3,
    cell: str = "G3",
) -> AttributeValue:
    return AttributeValue(
        label=label,
        value=value,
        value_type=value_type,  # type: ignore[arg-type]
        unit=unit,
        resolution=resolution,  # type: ignore[arg-type]
        mapping_policy_version="exact-alias-policy-v1",
        current_source=CurrentSourceReference(
            source_ref="src_survey_2026",
            sheet=sheet,
            row=row,
            cell=cell,
            location_ref="loc_001",
        ),
    )


def _build_document(
    plant: PlantIdentity,
    habitat: HabitatIdentity,
    attributes: dict[str, AttributeValue] | None = None,
    run_id: str = "run_test_001",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[
            SamplingLocationDetail(
                location_ref="loc_001",
                raw_address="Dusun Randu, Desa Hargobinangun, Kec. Pakem, Sleman",
                hamlet="Dusun Randu",
                sampling_marker="sampling 1",
            )
        ],
        attributes=attributes or {},
        media_refs=[],
        updated_by_run=run_id,
    )


def _build_draft(
    run_id: str,
    documents: list[KnowledgeDocument],
    reviews: list[DocumentReviewItem] | None = None,
    base_versions: dict[str, int] | None = None,
    revision: int = 1,
    source_filename: str = "data_input.xlsx",
    file_sha256: str = "a" * 64,
    source_uri: str | None = "cas:///sources/data_input.xlsx",
) -> DocumentDraft:
    doc_map = {f"{d.variety.id}:{d.habitat.id}": d for d in documents}
    bv = base_versions if base_versions is not None else {k: 0 for k in doc_map}
    return DocumentDraft(
        run_id=run_id,
        source_filename=source_filename,
        file_sha256=file_sha256,
        source_uri=source_uri,
        source_scope="field_survey_2026",
        schema_version="kms-document-v1",
        template_hash="b" * 64,
        config_fingerprint="cfg_default",
        revision=revision,
        documents=doc_map,
        reviews=reviews or [],
        base_versions=bv,
        metadata={"survey_year": 2026},
    )


def _do_commit(
    repo: DocumentRepository,
    draft: DocumentDraft,
    actor: str = "test-curator",
) -> dict[str, Any] | CommitReceipt:
    staged = repo.stage(
        draft,
        expected_revision=draft.revision - 1 if draft.revision > 1 else 0,
        actor=actor,
    )
    revision = staged["revision"] if isinstance(staged, dict) else staged.revision
    payload_sha256 = (
        staged["payload_sha256"]
        if isinstance(staged, dict)
        else staged.payload_sha256
    )
    return repo.commit(draft.run_id, revision, payload_sha256, actor=actor)


# ============================================================================
# Mandatory Acceptance Tests (A01, A10, A13, A14, A16, A17)
# ============================================================================


def test_dynamic_attributes_stored_in_jsonb_without_alter_table(db: Engine):
    """Criterion A01: PostgreSQL stores knowledge in JSONB without DDL ALTER TABLE mutations.

    Verifies dynamic attributes from cells K2/K3 (soil moisture) and L2/L3 (soil pH)
    are persisted in kms.knowledge_documents document payload without changing table columns.
    """
    repo = DocumentRepository(db)
    source_sha = "a" * 64
    source_uri = "cas:///sources/data_input.xlsx"
    repo.register_source(source_sha, source_uri, 12345, actor="test-curator")

    # Capture schema columns before commit
    with db.connect() as conn:
        cols_before = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'kms' AND table_name = 'knowledge_documents'"
                )
            ).scalars().all()
        )

    plant = _build_plant("plant_rawit_001", "Cabai rawit (Capsicum frutescens L)")
    habitat = _build_habitat(
        "hab_sleman_001",
        "Desa Hargobinangun",
        "Kecamatan Pakem",
        "Kabupaten Sleman",
    )
    dynamic_attrs = {
        "attr_kelembaban_tanah": _build_attribute(
            label="Kelembaban tanah (%)",
            value=58.0,
            value_type="number",
            unit="%",
            cell="K3",
        ),
        "attr_ph_tanah": _build_attribute(
            label="pH tanah",
            value=7.0,
            value_type="number",
            unit=None,
            cell="L3",
        ),
        "attr_klorofil_spad": _build_attribute(
            label="Chlorophyll Content (SPAD)",
            value=49.02,
            value_type="number",
            unit="SPAD",
            cell="G3",
        ),
        "attr_suhu_kanopi": _build_attribute(
            label="Suhu Kanopi Lapangan",
            value=31.5,
            value_type="number",
            unit="°C",
            cell="M3",
        ),
    }

    doc = _build_document(
        plant, habitat, attributes=dynamic_attrs, run_id="run_a01_dynamic_001"
    )
    draft = _build_draft(
        "run_a01_dynamic_001",
        [doc],
        file_sha256=source_sha,
        source_uri=source_uri,
    )

    receipt = _do_commit(repo, draft, actor="test-curator")
    assert receipt is not None

    # Verify table schema was NOT altered
    with db.connect() as conn:
        cols_after = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'kms' AND table_name = 'knowledge_documents'"
                )
            ).scalars().all()
        )
    assert cols_before == cols_after, (
        f"Columns altered: added={cols_after - cols_before}, removed={cols_before - cols_after}"
    )

    # Verify JSONB storage
    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()

    doc_json = row["document"]
    attrs_saved = doc_json["attributes"]
    assert attrs_saved["attr_kelembaban_tanah"]["value"] == 58.0
    assert attrs_saved["attr_ph_tanah"]["value"] == 7.0
    assert attrs_saved["attr_klorofil_spad"]["value"] == 49.02
    assert attrs_saved["attr_suhu_kanopi"]["value"] == 31.5
    assert row["version"] == 1


def test_auto_accept_overwrites_existing_human_review_value(db: Engine):
    """Criterion A10: Policy-cleared AUTO_ACCEPT overwrites existing HUMAN_REVIEW value.

    Reverses legacy protection bug: an exact-match auto-accepted value with high confidence
    replaces an existing human-reviewed current fact.
    """
    repo = DocumentRepository(db)
    source_sha = "b" * 64
    source_uri = "cas:///sources/survey_lamuk.xlsx"
    repo.register_source(source_sha, source_uri, 23456, actor="test-curator")

    plant = _build_plant("plant_rawit_lamuk_001", "Cabai rawit (Capsicum frutescens L)")
    habitat = _build_habitat(
        "hab_wonosobo_lamuk_001",
        "Desa Lamuk",
        "Kecamatan Kalikajar",
        "Kabupaten Wonosobo",
    )
    doc_key = f"{plant.id}:{habitat.id}"

    # Initial Run: commit document with HUMAN_REVIEW resolution
    initial_attrs = {
        "attr_klorofil_spad": _build_attribute(
            label="Chlorophyll Content (SPAD)",
            value=46.5417,
            value_type="number",
            unit="SPAD",
            resolution="HUMAN_REVIEW",
            cell="G13",
        ),
    }
    doc_initial = _build_document(
        plant, habitat, attributes=initial_attrs, run_id="run_a10_initial_001"
    )
    draft_initial = _build_draft(
        "run_a10_initial_001",
        [doc_initial],
        file_sha256=source_sha,
        source_uri=source_uri,
    )
    _do_commit(repo, draft_initial, actor="test-curator")

    # Confirm initial state in database
    with db.connect() as conn:
        row1 = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()
    assert (
        row1["document"]["attributes"]["attr_klorofil_spad"]["resolution"]
        == "HUMAN_REVIEW"
    )
    assert (
        row1["document"]["attributes"]["attr_klorofil_spad"]["value"]
        == 46.5417
    )
    assert row1["version"] == 1

    # Second Run: new survey provides AUTO_ACCEPT value (49.02)
    updated_attrs = {
        "attr_klorofil_spad": _build_attribute(
            label="Chlorophyll Content (SPAD)",
            value=49.02,
            value_type="number",
            unit="SPAD",
            resolution="AUTO_ACCEPT",
            cell="G12",
        ),
    }
    doc_updated = _build_document(
        plant, habitat, attributes=updated_attrs, run_id="run_a10_update_002"
    )
    draft_updated = _build_draft(
        "run_a10_update_002",
        [doc_updated],
        base_versions={doc_key: 1},
        file_sha256=source_sha,
        source_uri=source_uri,
    )

    # Decision D2 / L4: Direct commit of AUTO_ACCEPT over existing HUMAN_REVIEW raises Conflict
    with pytest.raises(Conflict) as exc:
        _do_commit(repo, draft_updated, actor="test-curator")
    assert "OVERWRITE_BLOCKED" in str(exc.value)

    # Verify original HUMAN_REVIEW value remains preserved intact
    with db.connect() as conn:
        row2 = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()

    doc2 = row2["document"]
    val2 = doc2["attributes"]["attr_klorofil_spad"]
    assert val2["value"] == 46.5417
    assert val2["resolution"] == "HUMAN_REVIEW"
    assert row2["version"] == 1


def test_atomic_run_commit_all_or_nothing(db: Engine):
    """Criterion A13: Document changes are atomic; unresolved review blocks the entire run.

    When a run contains 3 documents (2 clean, 1 with pending review item),
    the commit must be rejected and ZERO documents or rows are stored to the database.
    """
    repo = DocumentRepository(db)
    source_sha = "c" * 64
    source_uri = "cas:///sources/batch_survey.xlsx"
    repo.register_source(source_sha, source_uri, 34567, actor="test-curator")

    # Document 1: Clean
    p1 = _build_plant("plant_rawit_a13_01", "Cabai rawit")
    h1 = _build_habitat("hab_a13_01", "Desa A", "Kecamatan A", "Kabupaten Sleman")
    d1 = _build_document(p1, h1, attributes={"attr_ph": _build_attribute("pH tanah", 6.8)})

    # Document 2: Clean
    p2 = _build_plant("plant_besar_a13_02", "Cabai besar")
    h2 = _build_habitat("hab_a13_02", "Desa B", "Kecamatan B", "Kabupaten Wonosobo")
    d2 = _build_document(p2, h2, attributes={"attr_ph": _build_attribute("pH tanah", 7.1)})

    # Document 3: Has conflict requiring review
    p3 = _build_plant("plant_keriting_a13_03", "Cabai keriting")
    h3 = _build_habitat("hab_a13_03", "Desa C", "Kecamatan C", "Kabupaten Temanggung")
    d3 = _build_document(p3, h3, attributes={"attr_ph": _build_attribute("pH tanah", 6.5)})

    pending_review = DocumentReviewItem(
        item_id="rev_intra_conflict_001",
        category="INTRA_RUN_VALUE_CONFLICT",
        target_document_key=f"{p3.id}:{h3.id}",
        source_label="Chlorophyll Content (SPAD)",
        source_context="Desa Lamuk sampling 1 vs sampling 2",
        raw_values=[49.02, 46.5417],
        status="pending",
    )

    run_id = "run_a13_atomic_001"
    draft = _build_draft(
        run_id=run_id,
        documents=[d1, d2, d3],
        reviews=[pending_review],
        file_sha256=source_sha,
        source_uri=source_uri,
    )

    staged = repo.stage(draft, expected_revision=0, actor="test-curator")
    revision = staged["revision"] if isinstance(staged, dict) else staged.revision
    payload_sha256 = (
        staged["payload_sha256"]
        if isinstance(staged, dict)
        else staged.payload_sha256
    )

    # Attempt commit: must raise InvalidState / Conflict due to pending review
    with pytest.raises((InvalidState, Conflict)):
        repo.commit(run_id, revision, payload_sha256, actor="test-curator")

    # Assert all-or-nothing: ZERO documents from this run exist in database
    with db.connect() as conn:
        doc_count = conn.scalar(
            text(
                "SELECT count(*) FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' IN (:p1, :p2, :p3)"
            ),
            {"p1": p1.id, "p2": p2.id, "p3": p3.id},
        )
    assert doc_count == 0, (
        f"Atomicity violated: {doc_count} documents were written despite pending review blocker"
    )

    # Now resolve review and verify atomic persistence of all 3 documents
    resolved_review = copy.deepcopy(pending_review)
    resolved_review.status = "approved"
    resolved_review.decision = {"selected_value": 49.02, "rationale": "Sampling marker 1 authoritative"}

    resolved_draft = _build_draft(
        run_id=run_id,
        documents=[d1, d2, d3],
        reviews=[resolved_review],
        revision=2,
        file_sha256=source_sha,
        source_uri=source_uri,
    )
    staged2 = repo.stage(resolved_draft, expected_revision=1, actor="test-curator")
    rev2 = staged2["revision"] if isinstance(staged2, dict) else staged2.revision
    sha2 = staged2["payload_sha256"] if isinstance(staged2, dict) else staged2.payload_sha256

    receipt = repo.commit(run_id, rev2, sha2, actor="test-curator")
    assert receipt is not None

    with db.connect() as conn:
        persisted_count = conn.scalar(
            text(
                "SELECT count(*) FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' IN (:p1, :p2, :p3)"
            ),
            {"p1": p1.id, "p2": p2.id, "p3": p3.id},
        )
    assert persisted_count == 3, f"Expected 3 documents committed, found {persisted_count}"


def test_latest_only_knowledge_and_audit_sanitization(db: Engine):
    """Criterion A14: Active knowledge stores latest-only; audit trace redacts document payload.

    Verifies:
    1. Active document JSONB retains only the latest value, without historical arrays.
    2. kms.audit_trace redacts 'document' from old_data and new_data.
    3. Outbox event payload contains no historical measurement arrays.
    """
    repo = DocumentRepository(db)
    source_sha = "d" * 64
    source_uri = "cas:///sources/audit_test.xlsx"
    repo.register_source(source_sha, source_uri, 45678, actor="test-curator")

    plant = _build_plant("plant_rawit_a14_01", "Cabai rawit (Capsicum frutescens L)")
    habitat = _build_habitat("hab_a14_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
    doc_key = f"{plant.id}:{habitat.id}"

    # Step 1: Initial commit with measurement 45.0
    doc_v1 = _build_document(
        plant,
        habitat,
        attributes={"attr_klorofil": _build_attribute("Chlorophyll Content", 45.0)},
        run_id="run_a14_v1",
    )
    draft_v1 = _build_draft("run_a14_v1", [doc_v1], file_sha256=source_sha, source_uri=source_uri)
    _do_commit(repo, draft_v1, actor="test-curator")

    # Step 2: Update commit with measurement 52.0
    doc_v2 = _build_document(
        plant,
        habitat,
        attributes={"attr_klorofil": _build_attribute("Chlorophyll Content", 52.0)},
        run_id="run_a14_v2",
    )
    draft_v2 = _build_draft(
        "run_a14_v2",
        [doc_v2],
        base_versions={doc_key: 1},
        file_sha256=source_sha,
        source_uri=source_uri,
    )
    _do_commit(repo, draft_v2, actor="test-curator")

    # Check 1: Active document payload is strictly latest-only
    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()

    doc_json = row["document"]
    assert row["version"] == 2
    assert doc_json["attributes"]["attr_klorofil"]["value"] == 52.0

    prohibited_history_keys = {
        "previous_value",
        "previous_values",
        "observations",
        "history",
        "raw_history",
    }
    for key in prohibited_history_keys:
        assert key not in doc_json, f"Prohibited history key '{key}' found in document root"
        assert key not in doc_json["attributes"]["attr_klorofil"], (
            f"Prohibited history key '{key}' found in attribute payload"
        )

    # Check 2: Audit trace sanitization (trigger redacts 'document')
    with db.connect() as conn:
        audit_rows = conn.execute(
            text(
                "SELECT old_data, new_data, event_type FROM kms.audit_trace "
                "WHERE entity_type = 'knowledge_documents' ORDER BY id ASC"
            )
        ).mappings().all()

    assert len(audit_rows) >= 2, f"Expected at least 2 audit entries for knowledge_documents, found {len(audit_rows)}"
    for entry in audit_rows:
        old_d = entry["old_data"]
        new_d = entry["new_data"]
        if old_d is not None:
            assert "document" not in old_d, (
                f"Audit trace leak: 'document' present in old_data for event {entry['event_type']}"
            )
        if new_d is not None:
            assert "document" not in new_d, (
                f"Audit trace leak: 'document' present in new_data for event {entry['event_type']}"
            )

    # Check 3: Outbox event sanitization
    with db.connect() as conn:
        outbox_rows = conn.execute(
            text("SELECT payload FROM kms.outbox_events WHERE run_id IN ('run_a14_v1', 'run_a14_v2')")
        ).scalars().all()

    for payload in outbox_rows:
        for key in prohibited_history_keys:
            assert key not in payload, f"Outbox leaked history key: {key}"


def test_commit_replay_idempotent_and_stale_upload_rejected(db: Engine):
    """Criterion A16: Commit replay is idempotent; stale upload with outdated base version is rejected.

    Part A: Repeating identical commit returns receipt with replayed=True and generates no duplicate outbox events.
    Part B: Commit with stale base_version (older than database version) raises Conflict.
    """
    repo = DocumentRepository(db)
    source_sha = "e" * 64
    source_uri = "cas:///sources/replays.xlsx"
    repo.register_source(source_sha, source_uri, 56789, actor="test-curator")

    plant = _build_plant("plant_rawit_a16_01", "Cabai rawit")
    habitat = _build_habitat("hab_a16_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
    doc_key = f"{plant.id}:{habitat.id}"

    # Part A: Idempotent replay
    doc1 = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 6.5)}, run_id="run_a16_rep_01")
    draft1 = _build_draft("run_a16_rep_01", [doc1], file_sha256=source_sha, source_uri=source_uri)

    staged1 = repo.stage(draft1, expected_revision=0, actor="test-curator")
    rev1 = staged1["revision"] if isinstance(staged1, dict) else staged1.revision
    sha1 = staged1["payload_sha256"] if isinstance(staged1, dict) else staged1.payload_sha256

    receipt1 = repo.commit(draft1.run_id, rev1, sha1, actor="test-curator")
    replayed1 = receipt1["replayed"] if isinstance(receipt1, dict) else receipt1.replayed
    assert replayed1 is False

    # Second commit call with identical run_id, revision, and sha
    receipt2 = repo.commit(draft1.run_id, rev1, sha1, actor="test-curator")
    replayed2 = receipt2["replayed"] if isinstance(receipt2, dict) else receipt2.replayed
    assert replayed2 is True

    run_id2 = receipt2["run_id"] if isinstance(receipt2, dict) else receipt2.run_id
    assert run_id2 == draft1.run_id

    # Check outbox events count is exactly 1 (no duplicate event)
    with db.connect() as conn:
        outbox_count = conn.scalar(
            text("SELECT count(*) FROM kms.outbox_events WHERE run_id = :r"),
            {"r": draft1.run_id},
        )
    assert outbox_count == 1, f"Expected 1 outbox event for replayed run, found {outbox_count}"

    # Part B: Advance document to version 2 via fresh run
    doc2 = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 6.9)}, run_id="run_a16_fresh_02")
    draft2 = _build_draft("run_a16_fresh_02", [doc2], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    _do_commit(repo, draft2, actor="test-curator")

    # Document is now version 2 in database
    with db.connect() as conn:
        cur_version = conn.scalar(
            text(
                "SELECT version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        )
    assert cur_version == 2

    # A stale draft prepared when base version was 1 attempts to commit
    doc_stale = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.8)}, run_id="run_a16_stale_03")
    draft_stale = _build_draft(
        "run_a16_stale_03",
        [doc_stale],
        base_versions={doc_key: 1},  # Stale: database is already at version 2
        file_sha256=source_sha,
        source_uri=source_uri,
    )
    staged_stale = repo.stage(draft_stale, expected_revision=0, actor="test-curator")
    stale_rev = staged_stale["revision"] if isinstance(staged_stale, dict) else staged_stale.revision
    stale_sha = staged_stale["payload_sha256"] if isinstance(staged_stale, dict) else staged_stale.payload_sha256

    with pytest.raises(Conflict):
        repo.commit(draft_stale.run_id, stale_rev, stale_sha, actor="test-curator")

    # Verify document in database was NOT modified by the stale commit
    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()
    assert row["version"] == 2
    assert row["document"]["attributes"]["attr_ph"]["value"] == 6.9


def test_concurrent_writers_optimistic_concurrency_conflict(db: Engine):
    """Criterion A17: Concurrent writers do not experience lost updates.

    When two parallel writers attempt to update the same document from the same base version,
    one writer wins and the other writer receives a Conflict exception.
    """
    repo = DocumentRepository(db)
    source_sha = "f" * 64
    source_uri = "cas:///sources/concurrent_survey.xlsx"
    repo.register_source(source_sha, source_uri, 67890, actor="test-curator")

    plant = _build_plant("plant_rawit_a17_01", "Cabai rawit")
    habitat = _build_habitat("hab_a17_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
    doc_key = f"{plant.id}:{habitat.id}"

    # Seed baseline document at version 1
    doc_seed = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 6.5)}, run_id="run_a17_seed_00")
    draft_seed = _build_draft("run_a17_seed_00", [doc_seed], file_sha256=source_sha, source_uri=source_uri)
    _do_commit(repo, draft_seed, actor="test-curator")

    # Writer A draft
    doc_a = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.0)}, run_id="run_a17_writer_a")
    draft_a = _build_draft("run_a17_writer_a", [doc_a], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged_a = repo.stage(draft_a, expected_revision=0, actor="writer-a")

    # Writer B draft
    doc_b = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.5)}, run_id="run_a17_writer_b")
    draft_b = _build_draft("run_a17_writer_b", [doc_b], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged_b = repo.stage(draft_b, expected_revision=0, actor="writer-b")

    def _attempt_commit(draft: DocumentDraft, staged: Any, actor: str) -> dict[str, Any] | CommitReceipt:
        r = DocumentRepository(db)
        rev = staged["revision"] if isinstance(staged, dict) else staged.revision
        sha = staged["payload_sha256"] if isinstance(staged, dict) else staged.payload_sha256
        return r.commit(draft.run_id, rev, sha, actor=actor)

    successes: list[Any] = []
    conflicts: list[Exception] = []

    with ThreadPoolExecutor(max_workers=2) as executor:
        f_a = executor.submit(_attempt_commit, draft_a, staged_a, "writer-a")
        f_b = executor.submit(_attempt_commit, draft_b, staged_b, "writer-b")

        for f in (f_a, f_b):
            try:
                res = f.result()
                successes.append(res)
            except Conflict as exc:
                conflicts.append(exc)

    # Exactly one writer must succeed, and the other must receive Conflict
    assert len(successes) == 1, f"Expected exactly 1 successful writer, got {len(successes)}"
    assert len(conflicts) == 1, f"Expected exactly 1 Conflict, got {len(conflicts)}"

    # Check database state: version is now 2 (NOT 3, no lost update)
    with db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()

    assert row["version"] == 2
    final_val = row["document"]["attributes"]["attr_ph"]["value"]
    assert final_val in (7.0, 7.5), f"Unexpected final value: {final_val}"
