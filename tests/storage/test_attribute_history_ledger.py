"""Integration tests for Temuan 4: Append-only document attribute change ledger.

Covers:
- Transactional recording of old and new attribute values to kms.document_attribute_changes upon overwrite commit.
- Verification that trigger reject_mutation forbids UPDATE, DELETE, and TRUNCATE.
"""

from __future__ import annotations

import os
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
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_repository import DocumentRepository
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


def _build_habitat(
    hab_id: str, village: str, district: str, regency: str, province: str = "Jawa Tengah"
) -> HabitatIdentity:
    return HabitatIdentity(
        id=hab_id,
        label=f"Desa {village}, Kec. {district}, {regency}",
        administrative_path={
            "province_name": province,
            "regency_name": regency,
            "district_name": district,
            "village_name": village,
        },
    )


def _build_attr(
    label: str,
    value: any,
    value_type: str = "number",
    unit: str | None = None,
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
            source_ref="src_ledger_test.xlsx",
            sheet="Resume Data",
            row=2,
            cell="B2",
            location_ref="loc_001",
        ),
    )


def _build_doc(
    plant: PlantIdentity,
    habitat: HabitatIdentity,
    attributes: dict[str, AttributeValue],
    run_id: str = "run_ledger_001",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[
            SamplingLocationDetail(
                location_ref="loc_001",
                raw_address="Dusun Candisari, Desa Candibinangun, Sleman",
                hamlet="Dusun Candisari",
                sampling_marker="marker 1",
            )
        ],
        attributes=attributes,
        media_refs=[],
        updated_by_run=run_id,
    )


def _build_draft(
    run_id: str,
    documents: list[KnowledgeDocument],
    reviews: list[DocumentReviewItem] | None = None,
    base_versions: dict[str, int] | None = None,
    source_filename: str = "survey_ledger.xlsx",
    file_sha256: str = "1" * 64,
    source_uri: str = "cas:///sources/survey_ledger.xlsx",
) -> DocumentDraft:
    doc_map = {f"{d.variety.id}:{d.habitat.id}": d for d in documents}
    bv = base_versions if base_versions is not None else {k: 0 for k in doc_map}
    return DocumentDraft(
        run_id=run_id,
        source_filename=source_filename,
        file_sha256=file_sha256,
        source_uri=source_uri,
        source_scope="audit_ledger_test",
        schema_version="kms-document-v1",
        template_hash="2" * 64,
        config_fingerprint="cfg_audit_ledger",
        revision=1,
        documents=doc_map,
        reviews=reviews or [],
        base_versions=bv,
    )


def _do_commit(repo: DocumentRepository, draft: DocumentDraft, actor: str = "curator"):
    staged = repo.stage(draft, expected_revision=0, actor=actor)
    rev = staged["revision"] if isinstance(staged, dict) else staged.revision
    dig = staged["payload_sha256"] if isinstance(staged, dict) else staged.payload_sha256
    return repo.commit(draft.run_id, rev, dig, actor=actor)


def test_document_attribute_changes_logged_on_commit(db: Engine):
    """Temuan 4: Commit that overwrites an existing attribute logs old and new values to kms.document_attribute_changes."""
    repo = DocumentRepository(db)
    sha1 = "3" * 64
    repo.register_source(sha1, "cas:///sources/ledger_src1.xlsx", 5000, actor="curator-alpha")

    plant = _build_plant("plant_ledger_01", "Cabai Keriting Merah")
    habitat = _build_habitat("hab_ledger_01", "Candibinangun", "Pakem", "Sleman")
    doc_key = f"{plant.id}:{habitat.id}"

    # 1. Initial commit with tinggi_tanaman = 70.0
    attr_init = _build_attr("tinggi tanaman", 70.0, "number", "cm")
    doc_init = _build_doc(plant, habitat, {"attr_tinggi_tanaman": attr_init}, run_id="run_ledger_01")
    draft_init = _build_draft("run_ledger_01", [doc_init], file_sha256=sha1, source_uri="cas:///sources/ledger_src1.xlsx")
    _do_commit(repo, draft_init, actor="curator-alpha")

    # 2. Second commit updating tinggi_tanaman = 75.5
    sha2 = "4" * 64
    repo.register_source(sha2, "cas:///sources/ledger_src2.xlsx", 5000, actor="curator-beta")

    attr_update = _build_attr("tinggi tanaman", 75.5, "number", "cm")
    doc_update = _build_doc(plant, habitat, {"attr_tinggi_tanaman": attr_update}, run_id="run_ledger_02")
    draft_update = _build_draft(
        "run_ledger_02",
        [doc_update],
        base_versions={doc_key: 1},
        file_sha256=sha2,
        source_uri="cas:///sources/ledger_src2.xlsx",
    )
    _do_commit(repo, draft_update, actor="curator-beta")

    # 3. Verify ledger entry in kms.document_attribute_changes
    with db.connect() as conn:
        changes = conn.execute(
            text("""
                SELECT doc_id, attribute_id, old_value, new_value, run_id, actor
                FROM kms.document_attribute_changes
                WHERE doc_id = :doc_id AND attribute_id = 'attr_tinggi_tanaman'
                ORDER BY created_at DESC
            """),
            {"doc_id": doc_key},
        ).mappings().all()

    assert len(changes) == 1
    entry = changes[0]
    assert entry["doc_id"] == doc_key
    assert entry["attribute_id"] == "attr_tinggi_tanaman"
    assert entry["old_value"]["value"] == 70.0
    assert entry["new_value"]["value"] == 75.5
    assert entry["run_id"] == "run_ledger_02"
    assert entry["actor"] == "curator-beta"


def test_document_attribute_changes_trigger_rejects_mutation(db: Engine):
    """Temuan 4: kms.document_attribute_changes trigger reject_mutation blocks UPDATE, DELETE, and TRUNCATE."""
    with db.connect() as conn:
        # Insert a test change entry
        conn.execute(
            text("""
                INSERT INTO kms.document_attribute_changes
                (doc_id, attribute_id, old_value, new_value, run_id, actor)
                VALUES ('doc_test_sec', 'attr_tinggi_tanaman', '{"value": 10}', '{"value": 20}', 'run_sec', 'actor_sec')
            """)
        )
        conn.commit()

        # 1. UPDATE must be rejected by trigger reject_mutation
        with pytest.raises(Exception) as exc_update:
            conn.execute(
                text("UPDATE kms.document_attribute_changes SET actor = 'hacker' WHERE doc_id = 'doc_test_sec'")
            )
            conn.commit()
        assert "prohibited" in str(exc_update.value).lower()
        conn.rollback()

        # 2. DELETE must be rejected by trigger reject_mutation
        with pytest.raises(Exception) as exc_delete:
            conn.execute(
                text("DELETE FROM kms.document_attribute_changes WHERE doc_id = 'doc_test_sec'")
            )
            conn.commit()
        assert "prohibited" in str(exc_delete.value).lower()
        conn.rollback()

        # 3. TRUNCATE must be rejected by trigger reject_mutation
        with pytest.raises(Exception) as exc_truncate:
            conn.execute(text("TRUNCATE TABLE kms.document_attribute_changes"))
            conn.commit()
        assert "prohibited" in str(exc_truncate.value).lower()
        conn.rollback()
