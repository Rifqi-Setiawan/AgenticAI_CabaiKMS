"""Unit and integration tests for Temuan 3: can_overwrite policy enforcement.

Covers:
- unit sama -> boleh
- unit beda dimensi (cm vs kg) -> diblok ke review (UNIT_MISMATCH)
- tipe beda (number vs text) -> diblok ke review (OVERWRITE_BLOCKED)
- nilai HUMAN_REVIEW tidak diturunkan oleh AUTO_ACCEPT
- varietas+lokasi sama dengan atribut tambahan -> atribut lama utuh, atribut baru masuk, versi dokumen naik 1
"""

from __future__ import annotations

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
            source_ref="src_ow_test.xlsx",
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
    run_id: str = "run_ow_001",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[
            SamplingLocationDetail(
                location_ref="loc_001",
                raw_address="Dusun Karang, Desa Hargobinangun, Sleman",
                hamlet="Dusun Karang",
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
    source_filename: str = "survey_ow.xlsx",
    file_sha256: str = "c" * 64,
    source_uri: str = "cas:///sources/survey_ow.xlsx",
) -> DocumentDraft:
    doc_map = {f"{d.variety.id}:{d.habitat.id}": d for d in documents}
    bv = base_versions if base_versions is not None else {k: 0 for k in doc_map}
    return DocumentDraft(
        run_id=run_id,
        source_filename=source_filename,
        file_sha256=file_sha256,
        source_uri=source_uri,
        source_scope="audit_ow_test",
        schema_version="kms-document-v1",
        template_hash="d" * 64,
        config_fingerprint="cfg_audit_ow",
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


def test_can_overwrite_unit_sama_allowed():
    """Temuan 3b.1: Compatible units (cm vs cm) are permitted to overwrite existing value."""
    policy = AttributePolicy()
    exist = _build_attr("tinggi tanaman", 80.0, "number", "cm", "AUTO_ACCEPT")
    incoming = _build_attr("tinggi tanaman", 85.0, "number", "cm", "AUTO_ACCEPT")

    assert policy.can_overwrite(exist, incoming) is True


def test_can_overwrite_unit_beda_dimensi_blocked_to_review():
    """Temuan 3b.2: Incompatible dimension units (cm vs kg) block overwrite and create review item."""
    policy = AttributePolicy()
    exist = _build_attr("tinggi tanaman", 80.0, "number", "cm", "AUTO_ACCEPT")
    incoming = _build_attr("tinggi tanaman", 85.0, "number", "kg", "AUTO_ACCEPT")

    # Direct policy rejection
    assert policy.can_overwrite(exist, incoming) is False

    # Planner path integration: existing document has cm, incoming row has kg
    planner = DocumentPlanner(policy=policy)
    ar = AdministrativeRegistry()
    plant = PlantIdentity(id="plant_cabai_rawit", label="Cabai rawit", identity_level="species")
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    doc_key = f"{plant.id}:{habitat.id}"

    base_doc = _build_doc(plant, habitat, {"attr_tinggi_tanaman": exist})

    records = [
        {
            "_row": 2,
            "_sheet": "Resume Data",
            "Varietas": "Cabai Rawit",
            "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
            "tinggi tanaman": "85.0 kg",
        }
    ]

    draft = planner.plan_records(
        records,
        current_documents={doc_key: base_doc},
        run_id="run_unit_mismatch",
    )

    # Document attribute must be preserved as original (80.0 cm)
    planned_doc = draft.documents[doc_key]
    assert planned_doc.attributes["attr_tinggi_tanaman"].value == 80.0
    assert planned_doc.attributes["attr_tinggi_tanaman"].unit == "cm"

    # Review item must be generated for UNIT_MISMATCH
    ow_reviews = [r for r in draft.reviews if r.category in ("UNIT_MISMATCH", "OVERWRITE_BLOCKED")]
    assert len(ow_reviews) == 1
    rev = ow_reviews[0]
    assert rev.source_label == "tinggi tanaman"
    assert rev.raw_values == [80.0, 85.0]


def test_can_overwrite_tipe_beda_blocked_to_review():
    """Temuan 3b.3: Incompatible value types (number vs text) block overwrite and create review item."""
    policy = AttributePolicy()
    exist = _build_attr("tinggi tanaman", 80.0, "number", "cm", "AUTO_ACCEPT")
    incoming = _build_attr("tinggi tanaman", "sangat tinggi", "text", None, "AUTO_ACCEPT")

    # Direct policy rejection
    assert policy.can_overwrite(exist, incoming) is False

    # Planner path integration
    planner = DocumentPlanner(policy=policy)
    ar = AdministrativeRegistry()
    plant = PlantIdentity(id="plant_cabai_rawit", label="Cabai rawit", identity_level="species")
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    assert habitat is not None
    doc_key = f"{plant.id}:{habitat.id}"

    base_doc = _build_doc(plant, habitat, {"attr_tinggi_tanaman": exist})

    records = [
        {
            "_row": 3,
            "_sheet": "Resume Data",
            "Varietas": "Cabai Rawit",
            "Lokasi Sampling": "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman",
            "tinggi tanaman": "sangat tinggi",
        }
    ]

    draft = planner.plan_records(
        records,
        current_documents={doc_key: base_doc},
        run_id="run_type_mismatch",
    )

    # Document attribute must remain number 80.0
    planned_doc = draft.documents[doc_key]
    assert planned_doc.attributes["attr_tinggi_tanaman"].value == 80.0

    # Review item must be created
    ow_reviews = [r for r in draft.reviews if r.category == "OVERWRITE_BLOCKED"]
    assert len(ow_reviews) == 1
    rev = ow_reviews[0]
    assert rev.raw_values == [80.0, "sangat tinggi"]


def test_nilai_human_review_tidak_diturunkan_oleh_auto_accept():
    """Temuan 3b.4: Incoming measurement with HUMAN_REVIEW resolution cannot auto-overwrite existing value."""
    policy = AttributePolicy()
    exist = _build_attr("tinggi tanaman", 80.0, "number", "cm", "AUTO_ACCEPT")
    incoming_human = _build_attr("tinggi tanaman", 90.0, "number", "cm", "HUMAN_REVIEW")

    assert policy.can_overwrite(exist, incoming_human) is False


def test_varietas_lokasi_sama_atribut_tambahan(db: Engine):
    """Temuan 3b.5: Same variety + habitat with additional attribute keeps old attribute, adds new, increments version."""
    repo = DocumentRepository(db)
    sha1 = "e" * 64
    repo.register_source(sha1, "cas:///sources/run1.xlsx", 1000, actor="curator")

    plant = _build_plant("plant_cabai_merge_01", "Cabai Rawit Unggul")
    habitat = _build_habitat("hab_merge_01", "Hargobinangun", "Pakem", "Sleman")
    doc_key = f"{plant.id}:{habitat.id}"

    # Initial commit: has attribute A (tinggi_tanaman = 80.0)
    attr_a = _build_attr("tinggi tanaman", 80.0, "number", "cm")
    doc1 = _build_doc(plant, habitat, {"attr_tinggi_tanaman": attr_a}, run_id="run_merge_initial")
    draft1 = _build_draft("run_merge_initial", [doc1], file_sha256=sha1, source_uri="cas:///sources/run1.xlsx")
    _do_commit(repo, draft1, actor="curator")

    # Verify version 1
    with db.connect() as conn:
        row1 = conn.execute(
            text("SELECT document, version FROM kms.knowledge_documents WHERE id = :id"),
            {"id": doc_key},
        ).mappings().one()
    assert row1["version"] == 1
    assert "attr_tinggi_tanaman" in row1["document"]["attributes"]
    assert row1["document"]["attributes"]["attr_tinggi_tanaman"]["value"] == 80.0

    # Second commit: same variety and habitat, adds attribute B (warna_daun = "hijau")
    sha2 = "f" * 64
    repo.register_source(sha2, "cas:///sources/run2.xlsx", 1000, actor="curator")

    attr_b = _build_attr("warna daun", "hijau", "text", None)
    doc2 = _build_doc(plant, habitat, {"attr_warna_daun": attr_b}, run_id="run_merge_second")
    draft2 = _build_draft(
        "run_merge_second",
        [doc2],
        base_versions={doc_key: 1},
        file_sha256=sha2,
        source_uri="cas:///sources/run2.xlsx",
    )
    _do_commit(repo, draft2, actor="curator")

    # Verify version 2: old attribute intact, new attribute added
    with db.connect() as conn:
        row2 = conn.execute(
            text("SELECT document, version FROM kms.knowledge_documents WHERE id = :id"),
            {"id": doc_key},
        ).mappings().one()
    assert row2["version"] == 2
    attrs = row2["document"]["attributes"]
    assert "attr_tinggi_tanaman" in attrs, "Original attribute A must remain intact"
    assert attrs["attr_tinggi_tanaman"]["value"] == 80.0
    assert "attr_warna_daun" in attrs, "New attribute B must be added"
    assert attrs["attr_warna_daun"]["value"] == "hijau"
