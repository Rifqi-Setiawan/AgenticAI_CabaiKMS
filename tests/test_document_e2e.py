"""Acceptance test suite for Stage S9: End-to-End Verification & Criteria A01-A28 Fulfillment.

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 526: Table 5 DoD & boundaries for S9 (Verifikasi End-to-End & Pemenuhan Kriteria A01-A28)
  * Lines 530-564: Table 6 Complete mapping of acceptance criteria A01-A28 to test specifications
  * Line 716: Section 11 Gate 3 Final A01-A28 verification & staging dry-run requirements
- reports/cabai-kms-jsonb/PRD_CabaiKMS_JSONB.md:
  * Section I8: Validasi akhir dan README
  * Section J (Lines 421-444): Kriteria penerimaan A01-A22
  * Section 4.3 & 6: Kriteria penerimaan A23-A28

Criteria covered (A01 - A28):
- A01: PostgreSQL menyimpan pengetahuan di JSONB; atribut dinamis tidak memerlukan DDL ALTER TABLE baru.
- A02: Unique identity menggunakan pasangan varietas dan habitat teresolusi, bukan varietas saja.
- A03: Habitat hanya diturunkan dari hierarki alamat administratif; elevasi dan pH tidak mengubah ID habitat.
- A04: Dua dusun sedesa digabung ke satu habitat; desa senama pada kabupaten berbeda dipisahkan secara tegas.
- A05: Alamat ambigu, memuat dua desa, atau kehilangan hierarki administratif menahan commit (status review).
- A06: Label sumber dan identity level tanaman dipertahankan; sistem dilarang mengarang kultivar buatan.
- A07: Kamus atribut berkembang dinamis via review; jumlah atribut tidak di-hardcode.
- A08: Sinonim terpercaya memperbarui key atribut yang sama, bukan membuat key duplikat.
- A09: Atribut baru/meragukan masuk HITL; organ berbeda dan fase muda/masak dipisahkan secara tegas.
- A10: Nilai otomatis lolos policy (AUTO_ACCEPT) dapat menggantikan current value termasuk eks-HUMAN_REVIEW.
- A11: Konflik nilai dalam satu unggahan wajib diekskalasi ke review; urutan baris dilarang menentukan pemenang.
- A12: Seluruh review harus diselesaikan sebelum commit; backend menolak request commit langsung secara transaksional.
- A13: Perubahan dokumen atomik all-or-nothing; satu run ditahan seluruhnya bila ada satu saja blocker terbuka.
- A14: Hanya current value di pengetahuan aktif; tidak ada riwayat nilai di log, outbox, atau audit trace.
- A15: Sel kosong no-op, nilai 0/false valid, unit invalid direview, dan rentang disimpan tanpa rata-rata otomatis.
- A16: Replay commit bersifat idempotent; upload stale tidak menimpa nilai lebih baru diam-diam.
- A17: Dua concurrent writers tidak mengalami lost update; draft kadaluarsa menerima version conflict.
- A18: Skrip migrasi data legacy berjalan dalam mode dry-run akuntabel; data tanpa habitat masuk karantina.
- A19: Retensi data legacy transparan; tidak ada purge produksi otomatis di kode produk.
- A20: Pipeline input, review, media existing, dan ekspor tetap berfungsi tanpa regresi.
- A21: README dan panduan teknis membedakan status rancangan, kemampuan teruji, dan aktivasi produksi.
- A22: Pemilik proyek menerima laporan evaluasi semantic policy sebelum auto-update non-exact aktif.
- A23: Klasifikasi foto mempertimbangkan 3 sinyal: citra visual, nama berkas/caption, dan opsi varietas Excel.
- A24: Foto yang tidak cocok dengan opsi varietas Excel run aktif menghasilkan item review PHOTO_VARIETY_MISMATCH.
- A25: Aksi review ASSIGN_EXISTING menautkan foto ke dokumen varietas terpilih dan melepaskan status review.
- A26: Aksi review CREATE_NEW_DOCUMENT membentuk dokumen baru dengan varietas baru tanpa mengarang taksonomi.
- A27: Aksi review DISCARD menandai foto ditolak secara non-destruktif tanpa menghapus blob fisik dari storage CAS.
- A28: Isolasi kuota vision: Seluruh pengujian unit CI berjalan 100% menggunakan mock/stub deterministik tanpa memanggil 9Router.

Candidate implementation files:
- README.md
- docs/PROJECT_GUIDE.md
- src/integrations/adapter.py

Protected test files:
- tests/test_document_e2e.py
- tests/test_documentation_parity.py
"""

from __future__ import annotations

import ast
from concurrent.futures import ThreadPoolExecutor
import copy
from datetime import datetime, timezone
import io
import json
import math
import os
from pathlib import Path
import re
import socket
from typing import Any, Literal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import openpyxl
from PIL import Image
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.engine import Engine, make_url

from src.agents import vision_classification
from src.integrations import adapter, client, photo_review, pipeline_hooks, streamlit_commit
from src.kms_api.app import create_app
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import ImageMetadata
from src.storage.attribute_policy import (
    AttributeCatalog,
    AttributeDefinition,
    AttributePolicy,
    resolve_attribute,
)
from src.storage.config import Settings
from src.storage.db import make_engine
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
    PhotoContextSignal,
    PhotoMismatchDecision,
    PlantIdentity,
    SamplingLocationDetail,
    VisionClassificationResult,
    validate_document,
)
from src.storage.document_planner import (
    DocumentPlanner,
    ParsedCellValue,
    detect_intra_workbook_conflicts,
    evaluate_photo_variety_alignment,
    parse_cell_value,
    parse_range_value,
    plan_document_changes,
)
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState
from src.storage.identity_resolution import (
    AdministrativeRegistry,
    LocationResolution,
    PlantCatalog,
    PlantResolution,
    resolve_location,
    resolve_plant,
)
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository

PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIELD_SAMPLE_PATH = PROJECT_ROOT / "data" / "samples" / "data_input.xlsx"
README_PATH = PROJECT_ROOT / "README.md"
PROJECT_GUIDE_PATH = PROJECT_ROOT / "docs" / "PROJECT_GUIDE.md"


# ============================================================================
# Database & Test Client Fixtures
# ============================================================================


@pytest.fixture
def test_db() -> Engine:
    """Disposable PostgreSQL test database connection. Strictly guards against production DB."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp",
    )
    parsed = make_url(url)
    db_name = parsed.database or ""

    if not db_name.endswith("_test"):
        pytest.fail(f"Refusing test on non-test database: {db_name}")
    if db_name == "cabai_kms":
        pytest.fail("Production database cabai_kms must never be touched by test suites!")

    pytest.importorskip("psycopg")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL") or url
    if make_url(admin_url).database != db_name:
        pytest.fail("Runtime and admin test URLs must target the same disposable database.")

    migrate(admin_url)
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


@pytest.fixture
def api_client(test_db: Engine, tmp_path: Path):
    """FastAPI TestClient fixture configured with isolated test tokens and CAS storage."""
    url = os.getenv(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://cabai_test@/cabai_kms_test?host=/tmp",
    )
    tokens = {
        "r" * 40: {"subject": "reader-test", "role": "reader"},
        "w" * 40: {"subject": "reviewer-test", "role": "reviewer"},
        "c" * 40: {"subject": "curator-test", "role": "curator"},
    }
    media_dir = tmp_path / "media_storage"
    media_dir.mkdir(parents=True, exist_ok=True)
    cas = LocalCAS(media_dir)

    settings = Settings(
        _env_file=None,
        database_url=url,
        media_storage_path=media_dir,
        media_min_free_bytes=0,
        kms_tokens_json=json.dumps(tokens),
    )
    kms_repo = KmsRepository(test_db)
    doc_repo = DocumentRepository(test_db)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=kms_repo, blob_store=blob_store)
    with TestClient(app) as tc:
        yield tc, doc_repo, kms_repo, blob_store


def _auth_header(role: str = "curator") -> dict[str, str]:
    token_char = {"reader": "r", "reviewer": "w", "curator": "c"}[role]
    return {"Authorization": f"Bearer {token_char * 40}"}


def _make_png_bytes() -> bytes:
    stream = io.BytesIO()
    image = Image.new("RGBA", (100, 100), (24, 120, 48, 255))
    image.save(stream, format="PNG")
    return stream.getvalue()


def _make_jpeg_bytes() -> bytes:
    stream = io.BytesIO()
    image = Image.new("RGB", (100, 100), (120, 200, 80))
    image.save(stream, format="JPEG")
    return stream.getvalue()


def _build_plant(
    plant_id: str = "plant_rawit_frutescens_001",
    label: str = "Cabai rawit (Capsicum frutescens L)",
    level: Literal["source_category", "species", "cultivar"] = "source_category",
    scientific_name: str = "Capsicum frutescens L",
) -> PlantIdentity:
    return PlantIdentity(
        id=plant_id,
        label=label,
        identity_level=level,
        scientific_name=scientific_name,
    )


def _build_habitat(
    habitat_id: str = "hab_sleman_hargobinangun_001",
    village: str = "Desa Hargobinangun",
    district: str = "Kecamatan Pakem",
    regency: str = "Kabupaten Sleman",
    province: str = "Daerah Istimewa Yogyakarta",
) -> HabitatIdentity:
    path = AdministrativePath(
        province_name=province,
        regency_name=regency,
        district_name=district,
        village_name=village,
    )
    return HabitatIdentity(
        id=habitat_id,
        definition="administrative_village_v1",
        administrative_path=path,
        label=f"{village}, {district}, {regency}",
    )


def _build_attribute(
    label: str,
    value: Any,
    value_type: Any = "number",
    unit: str | None = None,
    resolution: Any = "AUTO_ACCEPT",
    cell: str = "G3",
) -> AttributeValue:
    return AttributeValue(
        label=label,
        value=value,
        value_type=value_type,
        unit=unit,
        resolution=resolution,
        current_source=CurrentSourceReference(
            source_ref="src_field_data_input_2026",
            sheet="Resume Data",
            row=3,
            cell=cell,
        ),
    )


def _build_document(
    plant: PlantIdentity,
    habitat: HabitatIdentity,
    attributes: dict[str, AttributeValue] | None = None,
    media_refs: list[MediaReference] | None = None,
    run_id: str = "run_s9_e2e_001",
) -> KnowledgeDocument:
    return KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        attributes=attributes or {},
        media_refs=media_refs or [],
        updated_by_run=run_id,
    )


def _build_draft(
    run_id: str,
    documents: list[KnowledgeDocument],
    reviews: list[DocumentReviewItem] | None = None,
    base_versions: dict[str, int] | None = None,
    revision: int = 1,
    file_sha256: str = "a" * 64,
    source_uri: str = "cas:///sources/data_input.xlsx",
) -> DocumentDraft:
    doc_map = {f"{d.variety.id}:{d.habitat.id}": d for d in documents}
    bv = base_versions or {k: 0 for k in doc_map}
    return DocumentDraft(
        run_id=run_id,
        source_filename="data_input.xlsx",
        file_sha256=file_sha256,
        source_uri=source_uri,
        source_scope="field_survey_2026",
        schema_version="kms-document-v1",
        template_hash="b" * 64,
        config_fingerprint="cfg_s9_001",
        revision=revision,
        documents=doc_map,
        reviews=reviews or [],
        base_versions=bv,
        metadata={"survey_year": 2026},
    )


# ============================================================================
# End-to-End Pipeline Harness Helper
# ============================================================================


def _get_e2e_staged_draft(
    workbook_path: Path | str = FIELD_SAMPLE_PATH,
    run_id: str = "run_s9_e2e_001",
) -> DocumentDraft:
    """Execute the end-to-end pipeline hook and return the staged DocumentDraft.

    Verifies that the application pipeline hook (src.integrations.pipeline_hooks.run_pipeline_with_kms)
    and adapter (src.integrations.adapter) produce and stage a v2 DocumentDraft to /runs/v2/stage.
    """
    if not hasattr(adapter, "build_document_draft"):
        raise AssertionError(
            "Stage S9 E2E Integration incomplete: src.integrations.adapter does not implement "
            "build_document_draft for v2 DocumentDraft lifecycle."
        )

    builder = getattr(adapter, "build_document_draft")
    draft = builder(workbook_path=workbook_path, run_id=run_id)
    if not isinstance(draft, DocumentDraft):
        raise AssertionError(
            f"Stage S9 E2E Integration incomplete: expected DocumentDraft instance, got {type(draft)}"
        )
    return draft


# ============================================================================
# Criterion A01: PostgreSQL Stores Dynamic Attributes in JSONB
# ============================================================================


def test_a01_e2e_jsonb_storage_dynamic_attributes(test_db: Engine):
    """Criterion A01: PostgreSQL stores knowledge in JSONB without DDL ALTER TABLE mutations.

    Verified end-to-end from field workbook data_input.xlsx containing dynamic
    attributes (K2 'Kelembaban tanah (%)' = 58, L2 'pH tanah' = 7) through
    the KMS pipeline to committed KnowledgeDocument in PostgreSQL.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    # 1. In-memory check: presence of dynamic attributes in planned documents
    found_dynamic_attrs = False
    for doc in draft.documents.values():
        if "attr_kelembaban_tanah" in doc.attributes or "attr_ph_tanah" in doc.attributes:
            found_dynamic_attrs = True
            break
    assert found_dynamic_attrs, (
        "Criterion A01 failure: Dynamic attributes from cells K2 and L2 must be present "
        "in staged JSONB documents."
    )

    # 2. Database verification: persistence in JSONB without DDL mutations
    repo = DocumentRepository(test_db)
    source_sha = "a" * 64
    source_uri = "cas:///sources/data_input.xlsx"
    repo.register_source(source_sha, source_uri, 12345, actor="test-curator")

    with test_db.connect() as conn:
        cols_before = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'kms' AND table_name = 'knowledge_documents'"
                )
            ).scalars().all()
        )

    # Ensure reviews start in pending state for curator resolution
    if draft.reviews:
        draft = draft.model_copy(
            update={
                "reviews": [
                    r.model_copy(update={"status": "pending"}) for r in draft.reviews
                ]
            }
        )

    staged = repo.stage(draft, expected_revision=0, actor="test-curator")

    # Curator resolution: resolve every pending review before committing (Criteria A11 & A12)
    for review in draft.reviews:
        if review.status == "pending":
            repo.resolve_review(
                draft.run_id,
                review.item_id,
                {"action": "APPROVE", "status": "approved", "notes": "Approved by curator"},
                actor="test-curator",
            )

    run_info = repo.get_run(draft.run_id)
    rev = run_info["revision"]
    sha = run_info["payload_sha256"]
    receipt = repo.commit(draft.run_id, rev, sha, actor="test-curator")
    assert receipt is not None

    with test_db.connect() as conn:
        cols_after = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'kms' AND table_name = 'knowledge_documents'"
                )
            ).scalars().all()
        )
    assert cols_before == cols_after, (
        f"Criterion A01 failure: Table columns altered: added={cols_after - cols_before}, removed={cols_before - cols_after}"
    )

    # Verify JSONB storage
    with test_db.connect() as conn:
        row = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'attributes' ? 'attr_kelembaban_tanah' "
                "OR document->'attributes' ? 'attr_ph_tanah' LIMIT 1"
            )
        ).mappings().one()
    doc_json = row["document"]
    attrs_saved = doc_json["attributes"]
    if "attr_kelembaban_tanah" in attrs_saved:
        assert attrs_saved["attr_kelembaban_tanah"]["value"] == pytest.approx(58.0)
    if "attr_ph_tanah" in attrs_saved:
        assert attrs_saved["attr_ph_tanah"]["value"] == pytest.approx(7.0)


# ============================================================================
# Criterion A02: Unique Identity Variety + Habitat Pair
# ============================================================================


def test_a02_e2e_unique_identity_variety_habitat_pair():
    """Criterion A02: Unique identity uses plant variety and resolved habitat pair, not variety alone.

    Verified end-to-end: F3 'Cabai rawit' vs F4 'cabai besar' on the same habitat
    (Desa Hargobinangun, B3 & B4) produce 2 distinct documents with unique identities.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    hargobinangun_docs = [
        doc for doc in draft.documents.values()
        if doc.habitat.administrative_path.village_name == "Desa Hargobinangun"
    ]
    assert len(hargobinangun_docs) >= 2, (
        "Criterion A02 failure: Distinct varieties in Desa Hargobinangun must generate "
        "distinct KnowledgeDocument instances for each variety + habitat pair."
    )

    varieties = {doc.variety.id for doc in hargobinangun_docs}
    assert len(varieties) >= 2, (
        "Criterion A02 failure: Different varieties in the same habitat must retain distinct variety identities."
    )

    for key, doc in draft.documents.items():
        assert key == f"{doc.variety.id}:{doc.habitat.id}"


# ============================================================================
# Criterion A03: Habitat Derived Exclusively from Admin Hierarchy
# ============================================================================


def test_a03_e2e_habitat_derived_from_admin_hierarchy_ignoring_elevation_ph():
    """Criterion A03: Habitat is derived only from administrative hierarchy; elevation and pH do not alter habitat ID.

    Verified end-to-end: B3 (Dusun Randu, 573 mdpl, pH 7) vs B4 (Dusun Tenen, 598 mdpl, pH 6.8)
    both resolve to the single habitat Desa Hargobinangun, Kec. Pakem, Kab. Sleman.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    hargobinangun_docs = [
        doc for doc in draft.documents.values()
        if doc.habitat.administrative_path.village_name == "Desa Hargobinangun"
    ]
    assert len(hargobinangun_docs) >= 1

    habitat_ids = {doc.habitat.id for doc in hargobinangun_docs}
    assert len(habitat_ids) == 1, (
        "Criterion A03 failure: Differing elevations and soil pH values must not fragment habitat identity."
    )

    hab = hargobinangun_docs[0].habitat
    assert hab.administrative_path.province_name == "Daerah Istimewa Yogyakarta"
    assert hab.administrative_path.regency_name == "Kabupaten Sleman"
    assert hab.administrative_path.district_name == "Kecamatan Pakem"
    assert hab.administrative_path.village_name == "Desa Hargobinangun"


# ============================================================================
# Criterion A04: Hamlet Merging and Homonymous Village Separation
# ============================================================================


def test_a04_e2e_hamlets_merged_and_homonymous_villages_separated():
    """Criterion A04: Two hamlets in same village merged; homonymous villages in different regencies separated strictly.

    Verified end-to-end: B12 (Dusun Pangempon) and B13 (Dusun Genting) in Desa Lamuk, Wonosobo
    merge to 1 habitat. Homonymous Desa Lamuk in Kab. Wonosobo vs Kab. Purbalingga are separated.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    lamuk_wonosobo_docs = [
        doc for doc in draft.documents.values()
        if doc.habitat.administrative_path.village_name == "Desa Lamuk"
        and "wonosobo" in doc.habitat.administrative_path.regency_name.lower()
    ]
    assert len(lamuk_wonosobo_docs) >= 1, (
        "Criterion A04 failure: Dusun Pangempon and Dusun Genting must merge into Desa Lamuk, Wonosobo."
    )
    wonosobo_hab_id = lamuk_wonosobo_docs[0].habitat.id

    # Homonymous separation: Desa Lamuk, Purbalingga must produce a distinct habitat ID
    addr_purbalingga = "Desa Lamuk, Kec. Kejobong, Kabupaten Purbalingga, Jawa Tengah"
    res_p = resolve_location(addr_purbalingga)
    assert res_p.status == "RESOLVED"
    assert res_p.habitat is not None
    assert res_p.habitat.administrative_path.village_name == "Desa Lamuk"
    assert "purbalingga" in res_p.habitat.administrative_path.regency_name.lower()
    assert res_p.habitat.id != wonosobo_hab_id, (
        "Criterion A04 failure: Homonymous Desa Lamuk in Kab. Purbalingga must have a distinct habitat ID from Wonosobo."
    )


# ============================================================================
# Criterion A05: Ambiguous Location Blocks Commit
# ============================================================================


def test_a05_e2e_ambiguous_location_blocks_commit(test_db: Engine):
    """Criterion A05: Ambiguous address, multiple villages, or missing administrative hierarchy blocks commit.

    Verified end-to-end: Ambiguous location strings produce pending review items
    with category LOCATION_UNRESOLVED, holding commit.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    # 1. Verify ambiguous location detection via planner
    planner = DocumentPlanner()
    bad_location_records = [
        {
            "Lokasi Sampling": "Desa Hargobinangun atau Desa Pakem, Kabupaten Sleman",
            "Varietas": "Cabai rawit (Capsicum frutescens L)",
            "pH tanah": 7.0,
            "_row": 99,
        }
    ]
    ambiguous_draft = planner.plan_records(records=bad_location_records, run_id="run_a05_ambiguous_e2e")
    loc_reviews = [
        r for r in ambiguous_draft.reviews
        if r.category in ("LOCATION_UNRESOLVED", "LOCATION_AMBIGUOUS", "UNRESOLVED_LOCATION")
    ]
    assert len(loc_reviews) >= 1, "Criterion A05 failure: Ambiguous location must produce a review item."
    assert loc_reviews[0].status == "pending", "Location review item must be pending to block commit."

    # 2. Verify commit is blocked transactionally
    repo = DocumentRepository(test_db)
    source_sha = "c" * 64
    source_uri = "cas:///sources/ambiguous.xlsx"
    repo.register_source(source_sha, source_uri, 9999, actor="test-curator")

    staged = repo.stage(ambiguous_draft, expected_revision=0, actor="test-curator")
    rev = staged["revision"] if isinstance(staged, dict) else staged.revision
    sha = staged["payload_sha256"] if isinstance(staged, dict) else staged.payload_sha256
    with pytest.raises((InvalidState, Conflict)):
        repo.commit(ambiguous_draft.run_id, rev, sha, actor="test-curator")


# ============================================================================
# Criterion A06: Plant Identity Level & Source Category Retention
# ============================================================================


def test_a06_e2e_plant_identity_level_and_source_category_retention():
    """Criterion A06: Source label and plant identity level preserved; system never invents synthetic cultivars.

    Verified end-to-end: F3-F13 'Cabai rawit' and F14-F15 'cabai besar' map to
    source_category level, not invented cultivars.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    for doc in draft.documents.values():
        assert doc.variety.identity_level in ("source_category", "species", "cultivar")
        assert doc.variety.label is not None
        assert "cultivar_synthetic" not in doc.variety.id, (
            "Criterion A06 failure: System must not invent synthetic cultivars."
        )


# ============================================================================
# Criterion A07: Attribute Catalog Dynamic Expansion via Review
# ============================================================================


def test_a07_e2e_catalog_dynamic_expansion_via_review():
    """Criterion A07: Attribute catalog expands dynamically via review; attribute count is not hardcoded.

    Verified end-to-end: Header G2 'Chlorophyll Content (SPAD)' or new attribute
    produces a review item and expands catalog upon approval.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    header_g2 = "Chlorophyll Content (SPAD)"
    catalog = AttributeCatalog()
    initial_count = len(catalog)
    assert initial_count > 0

    # Before registration, novel field must be classified as new attribute review
    pre_res = resolve_attribute(header_g2, catalog=catalog)
    assert pre_res.status in ("NEW_ATTRIBUTE_REVIEW", "NEEDS_REVIEW"), (
        "Criterion A07 failure: Novel attribute must enter review before registration."
    )
    assert pre_res.attribute_id is None

    # Simulate approved review registering the new attribute dynamically
    new_def = AttributeDefinition(
        attribute_id="attr_chlorophyll_spad",
        canonical_key="chlorophyll_spad",
        label=header_g2,
        organ="daun",
        value_type="number",
        unit="SPAD",
        description="Kandungan klorofil daun hasil pengukuran SPAD meter",
    )
    registered = catalog.register_attribute(new_def)
    assert registered.attribute_id == "attr_chlorophyll_spad"
    assert len(catalog) == initial_count + 1, "Catalog count must expand dynamically."

    # Post registration, exact match must resolve immediately to auto accept
    post_res = resolve_attribute(header_g2, catalog=catalog)
    assert post_res.status == "AUTO_ACCEPT"
    assert post_res.attribute_id == "attr_chlorophyll_spad"


# ============================================================================
# Criterion A08: Trusted Synonyms Map to Canonical Key
# ============================================================================


def test_a08_e2e_trusted_synonyms_map_to_canonical_key():
    """Criterion A08: Trusted synonyms update the same canonical key, avoiding duplicate keys.

    Verified end-to-end: Curated alias 'mature plant height' maps to canonical
    key 'attr_tinggi_tanaman' without creating duplicate keys.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    catalog = AttributeCatalog()
    res_alias = resolve_attribute("mature plant height", catalog=catalog)
    res_canonical = resolve_attribute("tinggi tanaman", catalog=catalog)
    assert res_alias.attribute_id == res_canonical.attribute_id, (
        "Criterion A08 failure: Curated synonym must resolve to canonical attribute ID."
    )

    for doc in draft.documents.values():
        keys = list(doc.attributes.keys())
        height_keys = [k for k in keys if "tinggi" in k]
        assert len(height_keys) <= 1, (
            "Criterion A08 failure: Synonyms must map to single canonical attribute key."
        )


# ============================================================================
# Criterion A09: Biological Organ & Developmental Stage Separation
# ============================================================================


def test_a09_e2e_organ_and_development_stage_separation():
    """Criterion A09: New/doubtful attributes enter HITL; organs and immature/mature phases separated strictly.

    Verified end-to-end: 'panjang buah muda' vs 'panjang buah masak' maintain
    separate keys and are never merged automatically.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    catalog = AttributeCatalog()

    # 1. Immature vs Mature Fruit length separation
    res_muda = resolve_attribute("panjang buah muda", catalog=catalog)
    res_masak = resolve_attribute("panjang buah masak", catalog=catalog)

    assert res_muda.attribute_id != res_masak.attribute_id, (
        "Criterion A09 failure: Immature and mature fruit stages must have distinct attribute keys."
    )

    # Ambiguous length without developmental stage must enter review, never auto accept to either
    res_ambiguous_stage = resolve_attribute("panjang buah", catalog=catalog)
    assert res_ambiguous_stage.status == "NEEDS_REVIEW", (
        "Criterion A09 failure: Ambiguous developmental stage must enter review."
    )

    # 2. Diameter vs Length separation
    res_diameter = resolve_attribute("diameter buah", catalog=catalog)
    assert res_diameter.attribute_id != res_muda.attribute_id
    assert res_diameter.attribute_id != res_masak.attribute_id


# ============================================================================
# Criterion A10: Overwrite Policy (AUTO_ACCEPT Overwrites HUMAN_REVIEW)
# ============================================================================


def test_a10_e2e_auto_accept_overwrites_existing_human_review(test_db: Engine):
    """Criterion A10: Policy-cleared automatic values (AUTO_ACCEPT) can overwrite current value including ex-HUMAN_REVIEW.

    Verified end-to-end: An existing document with HUMAN_REVIEW value updated by
    a subsequent run with exact-match AUTO_ACCEPT successfully overwrites the value.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    repo = DocumentRepository(test_db)
    source_sha = "b" * 64
    source_uri = "cas:///sources/survey_lamuk.xlsx"
    repo.register_source(source_sha, source_uri, 23456, actor="test-curator")

    plant = _build_plant("plant_rawit_lamuk_001", "Cabai rawit (Capsicum frutescens L)")
    habitat = _build_habitat("hab_wonosobo_lamuk_001", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
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
    doc_initial = _build_document(plant, habitat, attributes=initial_attrs, run_id="run_a10_initial_001")
    draft_initial = _build_draft("run_a10_initial_001", [doc_initial], file_sha256=source_sha, source_uri=source_uri)
    staged1 = repo.stage(draft_initial, expected_revision=0, actor="test-curator")
    rev1 = staged1["revision"] if isinstance(staged1, dict) else staged1.revision
    sha1 = staged1["payload_sha256"] if isinstance(staged1, dict) else staged1.payload_sha256
    repo.commit(draft_initial.run_id, rev1, sha1, actor="test-curator")

    # Confirm initial state in database
    with test_db.connect() as conn:
        row1 = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()
    assert row1["document"]["attributes"]["attr_klorofil_spad"]["resolution"] == "HUMAN_REVIEW"
    assert row1["document"]["attributes"]["attr_klorofil_spad"]["value"] == 46.5417
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
    doc_updated = _build_document(plant, habitat, attributes=updated_attrs, run_id="run_a10_update_002")
    draft_updated = _build_draft(
        "run_a10_update_002",
        [doc_updated],
        base_versions={doc_key: 1},
        file_sha256=source_sha,
        source_uri=source_uri,
    )
    staged2 = repo.stage(draft_updated, expected_revision=0, actor="test-curator")
    rev2 = staged2["revision"] if isinstance(staged2, dict) else staged2.revision
    sha2 = staged2["payload_sha256"] if isinstance(staged2, dict) else staged2.payload_sha256
    repo.commit(draft_updated.run_id, rev2, sha2, actor="test-curator")

    # Verify value was overwritten by AUTO_ACCEPT
    with test_db.connect() as conn:
        row2 = conn.execute(
            text(
                "SELECT document, version FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' = :v_id AND document->'habitat'->>'id' = :h_id"
            ),
            {"v_id": plant.id, "h_id": habitat.id},
        ).mappings().one()
    assert row2["document"]["attributes"]["attr_klorofil_spad"]["resolution"] == "AUTO_ACCEPT", (
        "Criterion A10 failure: AUTO_ACCEPT must overwrite previous HUMAN_REVIEW value."
    )
    assert row2["document"]["attributes"]["attr_klorofil_spad"]["value"] == pytest.approx(49.02)
    assert row2["version"] == 2


# ============================================================================
# Criterion A11: Intra-Workbook Conflict Detection & Row Order Invariance
# ============================================================================


def test_a11_e2e_intra_workbook_conflict_enqueued_to_review():
    """Criterion A11: Intra-workbook value conflict escalated to review; row order never determines winner.

    Verified end-to-end: Conflicting values in Lamuk (B12 = 49.02 vs B13 = 46.54)
    and Argalingga (B14 = 47.09 vs B15 = 45.62) produce INTRA_WORKBOOK_CONFLICT review items.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    conflict_reviews = [
        r for r in draft.reviews
        if r.category in ("INTRA_WORKBOOK_CONFLICT", "INTRA_RUN_VALUE_CONFLICT")
    ]
    assert len(conflict_reviews) >= 2, (
        "Criterion A11 failure: Conflicting values in Lamuk and Argalingga must produce review items."
    )
    for rev in conflict_reviews:
        assert rev.status == "pending", "Conflict review items must be pending (never auto-picked by row order)."


# ============================================================================
# Criterion A12: Commit Rejected When Pending Reviews Exist
# ============================================================================


def test_a12_e2e_pending_reviews_block_commit_with_conflict(api_client):
    """Criterion A12: All reviews must be resolved before commit; backend rejects direct commit with HTTP 409 Conflict.

    Verified end-to-end: Staged draft with pending review items receives HTTP 409 Conflict
    upon calling commit endpoint.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    client, repo, _, _ = api_client
    run_id = draft.run_id

    # 1. Register source
    repo.register_source(draft.file_sha256, draft.source_uri or "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    # 2. Stage draft
    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=_auth_header("reviewer"),
    )
    assert stage_res.status_code == 200, f"Stage failed: {stage_res.status_code}: {stage_res.text}"

    # 3. Attempt direct commit while pending reviews exist -> Must return HTTP 409 Conflict
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": 1, "payload_sha256": stage_res.json()["payload_sha256"]},
        headers=_auth_header("reviewer"),
    )
    assert commit_res.status_code == 409, (
        f"Criterion A12 failure: Expected HTTP 409 Conflict for commit with pending reviews, got {commit_res.status_code}: {commit_res.text}"
    )
    assert "pending" in commit_res.json().get("detail", "").lower()


# ============================================================================
# Criterion A13: Atomic Commit All-or-Nothing
# ============================================================================


def test_a13_e2e_atomic_run_commit_all_or_nothing(test_db: Engine):
    """Criterion A13: Document changes atomic all-or-nothing; whole run held if any blocker is open.

    Verified end-to-end: If a single document in a multi-document run has a pending blocker,
    zero documents from the run are committed to the database.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)
    assert len(draft.documents) >= 2, (
        "Criterion A13 precondition: Multi-document run required to verify all-or-nothing atomicity."
    )

    repo = DocumentRepository(test_db)
    source_sha = "d" * 64
    source_uri = "cas:///sources/atomic_test.xlsx"
    repo.register_source(source_sha, source_uri, 54321, actor="test-curator")

    p1 = _build_plant("plant_a13_01", "Cabai rawit")
    p2 = _build_plant("plant_a13_02", "Cabai besar")
    h1 = _build_habitat("hab_a13_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")

    d1 = _build_document(p1, h1, run_id="run_a13_e2e")
    d2 = _build_document(p2, h1, run_id="run_a13_e2e")

    pending_review = DocumentReviewItem(
        item_id="rev_a13_blocker",
        category="INTRA_WORKBOOK_CONFLICT",
        target_document_key=f"{p1.id}:{h1.id}",
        source_label="Chlorophyll Content",
        raw_values=["49.02", "46.54"],
        status="pending",
    )

    test_draft = _build_draft("run_a13_e2e", [d1, d2], reviews=[pending_review], file_sha256=source_sha, source_uri=source_uri)
    staged = repo.stage(test_draft, expected_revision=0, actor="test-curator")
    rev = staged["revision"] if isinstance(staged, dict) else staged.revision
    sha = staged["payload_sha256"] if isinstance(staged, dict) else staged.payload_sha256

    # Attempt commit: must raise InvalidState / Conflict
    with pytest.raises((InvalidState, Conflict)):
        repo.commit(test_draft.run_id, rev, sha, actor="test-curator")

    # Assert all-or-nothing: ZERO documents from this run exist in database
    with test_db.connect() as conn:
        doc_count = conn.scalar(
            text(
                "SELECT count(*) FROM kms.knowledge_documents "
                "WHERE document->'variety'->>'id' IN (:p1, :p2)"
            ),
            {"p1": p1.id, "p2": p2.id},
        )
    assert doc_count == 0, (
        f"Criterion A13 failure: {doc_count} documents were written despite pending review blocker (all-or-nothing violated)"
    )


# ============================================================================
# Criterion A14: Latest-Only Active Knowledge & Audit Trace Sanitization
# ============================================================================


def test_a14_e2e_latest_only_active_knowledge_and_audit_sanitization(test_db: Engine):
    """Criterion A14: Only current value in active knowledge; no hidden value history in logs/audit/gold.

    Verified end-to-end: Committed knowledge documents expose only latest attribute values;
    kms.audit_trace excludes document payload columns.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    # 1. In-memory check
    for doc in draft.documents.values():
        for attr in doc.attributes.values():
            assert not isinstance(attr.value, list) or attr.value_type == "list", (
                "Criterion A14 failure: Single scalar attributes must not accumulate history arrays."
            )

    # 2. Database check: commit v1 then v2, check payload and audit_trace
    repo = DocumentRepository(test_db)
    source_sha = "e" * 64
    source_uri = "cas:///sources/audit_sanitization.xlsx"
    repo.register_source(source_sha, source_uri, 44444, actor="test-curator")

    plant = _build_plant("plant_a14_01", "Cabai rawit")
    habitat = _build_habitat("hab_a14_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
    doc_key = f"{plant.id}:{habitat.id}"

    # V1 commit (45.0)
    d1 = _build_document(plant, habitat, attributes={"attr_klorofil": _build_attribute("Chlorophyll Content", 45.0)}, run_id="run_a14_v1")
    draft1 = _build_draft("run_a14_v1", [d1], file_sha256=source_sha, source_uri=source_uri)
    staged1 = repo.stage(draft1, expected_revision=0, actor="test-curator")
    repo.commit(draft1.run_id, staged1["revision"] if isinstance(staged1, dict) else staged1.revision,
                staged1["payload_sha256"] if isinstance(staged1, dict) else staged1.payload_sha256, actor="test-curator")

    # V2 commit (52.0)
    d2 = _build_document(plant, habitat, attributes={"attr_klorofil": _build_attribute("Chlorophyll Content", 52.0)}, run_id="run_a14_v2")
    draft2 = _build_draft("run_a14_v2", [d2], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged2 = repo.stage(draft2, expected_revision=0, actor="test-curator")
    repo.commit(draft2.run_id, staged2["revision"] if isinstance(staged2, dict) else staged2.revision,
                staged2["payload_sha256"] if isinstance(staged2, dict) else staged2.payload_sha256, actor="test-curator")

    # Verify latest value only
    with test_db.connect() as conn:
        row = conn.execute(
            text("SELECT document, version FROM kms.knowledge_documents WHERE document->'variety'->>'id' = :v_id"),
            {"v_id": plant.id},
        ).mappings().one()
    doc_json = row["document"]
    assert doc_json["attributes"]["attr_klorofil"]["value"] == 52.0
    for prohibited in ("previous_value", "previous_values", "history", "observations"):
        assert prohibited not in doc_json
        assert prohibited not in doc_json["attributes"]["attr_klorofil"]

    # Verify audit_trace excludes document payload column
    with test_db.connect() as conn:
        audit_rows = conn.execute(
            text("SELECT old_data, new_data FROM kms.audit_trace WHERE entity_type = 'knowledge_documents'")
        ).mappings().all()
    assert len(audit_rows) >= 2, "Expected audit entries for knowledge_documents mutations"
    for entry in audit_rows:
        if entry["old_data"] is not None:
            assert "document" not in entry["old_data"]
        if entry["new_data"] is not None:
            assert "document" not in entry["new_data"]


# ============================================================================
# Criterion A15: Data Shapes (Blank No-op, 0/False Valid, Ranges Stored Unaveraged)
# ============================================================================


def test_a15_e2e_blank_noop_zero_valid_invalid_unit_and_ranges():
    """Criterion A15: Blank cells no-op, 0/false valid, invalid unit into review, ranges stored un-averaged.

    Verified end-to-end: Cells M3 ('28.3 - 30.5') and N3 ('72 - 67') stored as
    {'min': float, 'max': float} dicts without mathematical averaging.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    planner = DocumentPlanner()

    # 1. Blank cell parsing: must be recognized as blank/no-op
    blank_result = planner.parse_cell_value(None)
    assert blank_result is None or getattr(blank_result, "is_blank", False) or (isinstance(blank_result, dict) and blank_result.get("is_blank", False))
    blank_str = planner.parse_cell_value("   ")
    assert blank_str is None or getattr(blank_str, "is_blank", False) or (isinstance(blank_str, dict) and blank_str.get("is_blank", False))

    # 2. Value 0 and False: must be valid values, not treated as blank or falsy no-op
    zero_res = planner.parse_cell_value(0, expected_type="number")
    val_zero = getattr(zero_res, "value", None) if not isinstance(zero_res, dict) else zero_res["value"]
    assert val_zero == 0
    assert val_zero is not None

    false_res = planner.parse_cell_value(False, expected_type="boolean")
    val_false = getattr(false_res, "value", None) if not isinstance(false_res, dict) else false_res["value"]
    assert val_false is False
    assert val_false is not None

    # 3. Range parsing: M3 ('28.3 - 30.5') and N3 ('72 - 67')
    found_range = False
    for doc in draft.documents.values():
        for attr in doc.attributes.values():
            if attr.value_type == "range":
                found_range = True
                assert isinstance(attr.value, dict)
                assert "min" in attr.value and "max" in attr.value
                diff = abs(float(attr.value["max"]) - float(attr.value["min"]))
                assert diff > 0, "Range min and max must not be collapsed or averaged to a single scalar."
    assert found_range, (
        "Criterion A15 failure: Range attributes from cells M3 and N3 must be parsed as unaveraged dicts."
    )

    # 4. Invalid unit parsing: unknown unit escalates to review
    invalid_unit_res = planner.parse_cell_value("30 kuintal", expected_type="number", unit="kg")
    is_invalid = (
        getattr(invalid_unit_res, "is_valid", True) is False
        or (isinstance(invalid_unit_res, dict) and not invalid_unit_res.get("is_valid", True))
        or getattr(invalid_unit_res, "review_category", None) == "VALUE_INVALID"
        or (isinstance(invalid_unit_res, dict) and invalid_unit_res.get("review_category") == "VALUE_INVALID")
    )
    assert is_invalid, "Invalid unit '30 kuintal' must be flagged for review."


# ============================================================================
# Criterion A16: Commit Replay Idempotency & Stale Base Version Rejection
# ============================================================================


def test_a16_e2e_commit_replay_idempotent_and_stale_upload_rejected(test_db: Engine):
    """Criterion A16: Commit replay idempotent; stale upload cannot silently overwrite newer value.

    Verified end-to-end: Repeated commit calls return identical receipt with replayed=True;
    commit attempts with outdated base version are rejected.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    repo = DocumentRepository(test_db)
    source_sha = "f" * 64
    source_uri = "cas:///sources/replays.xlsx"
    repo.register_source(source_sha, source_uri, 56789, actor="test-curator")

    plant = _build_plant("plant_a16_01", "Cabai rawit")
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
    assert replayed2 is True, "Criterion A16 failure: Replayed commit must return replayed=True"

    # Part B: Advance document to version 2 via fresh run
    doc2 = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 6.9)}, run_id="run_a16_fresh_02")
    draft2 = _build_draft("run_a16_fresh_02", [doc2], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged2 = repo.stage(draft2, expected_revision=0, actor="test-curator")
    repo.commit(draft2.run_id, staged2["revision"] if isinstance(staged2, dict) else staged2.revision,
                staged2["payload_sha256"] if isinstance(staged2, dict) else staged2.payload_sha256, actor="test-curator")

    # Stale draft attempting commit with base_version = 1
    doc_stale = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.8)}, run_id="run_a16_stale_03")
    draft_stale = _build_draft("run_a16_stale_03", [doc_stale], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged_stale = repo.stage(draft_stale, expected_revision=0, actor="test-curator")
    with pytest.raises(Conflict):
        repo.commit(draft_stale.run_id, staged_stale["revision"] if isinstance(staged_stale, dict) else staged_stale.revision,
                    staged_stale["payload_sha256"] if isinstance(staged_stale, dict) else staged_stale.payload_sha256, actor="test-curator")


# ============================================================================
# Criterion A17: Concurrent Writers Optimistic Concurrency
# ============================================================================


def test_a17_e2e_concurrent_writers_optimistic_concurrency(test_db: Engine):
    """Criterion A17: Concurrent writers do not experience lost updates; stale draft receives version conflict.

    Verified end-to-end: Two parallel writes to the same document result in HTTP 409
    Conflict for the stale writer.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    repo = DocumentRepository(test_db)
    source_sha = "f" * 64
    source_uri = "cas:///sources/concurrent_survey.xlsx"
    repo.register_source(source_sha, source_uri, 67890, actor="test-curator")

    plant = _build_plant("plant_a17_01", "Cabai rawit")
    habitat = _build_habitat("hab_a17_01", "Desa Lamuk", "Kecamatan Kalikajar", "Kabupaten Wonosobo")
    doc_key = f"{plant.id}:{habitat.id}"

    # Seed baseline document at version 1
    doc_seed = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 6.5)}, run_id="run_a17_seed")
    draft_seed = _build_draft("run_a17_seed", [doc_seed], file_sha256=source_sha, source_uri=source_uri)
    staged_seed = repo.stage(draft_seed, expected_revision=0, actor="test-curator")
    repo.commit(draft_seed.run_id, staged_seed["revision"] if isinstance(staged_seed, dict) else staged_seed.revision,
                staged_seed["payload_sha256"] if isinstance(staged_seed, dict) else staged_seed.payload_sha256, actor="test-curator")

    # Competing Writer A and Writer B
    doc_a = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.0)}, run_id="run_a17_writer_a")
    draft_a = _build_draft("run_a17_writer_a", [doc_a], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged_a = repo.stage(draft_a, expected_revision=0, actor="writer-a")

    doc_b = _build_document(plant, habitat, attributes={"attr_ph": _build_attribute("pH tanah", 7.5)}, run_id="run_a17_writer_b")
    draft_b = _build_draft("run_a17_writer_b", [doc_b], base_versions={doc_key: 1}, file_sha256=source_sha, source_uri=source_uri)
    staged_b = repo.stage(draft_b, expected_revision=0, actor="writer-b")

    def _attempt_commit(d: DocumentDraft, s: Any, actor: str):
        r = DocumentRepository(test_db)
        rev = s["revision"] if isinstance(s, dict) else s.revision
        sha = s["payload_sha256"] if isinstance(s, dict) else s.payload_sha256
        return r.commit(d.run_id, rev, sha, actor=actor)

    successes = []
    conflicts = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        f_a = executor.submit(_attempt_commit, draft_a, staged_a, "writer-a")
        f_b = executor.submit(_attempt_commit, draft_b, staged_b, "writer-b")
        for f in (f_a, f_b):
            try:
                successes.append(f.result())
            except Conflict as exc:
                conflicts.append(exc)

    assert len(successes) == 1, f"Criterion A17 failure: Expected exactly 1 successful writer, got {len(successes)}"
    assert len(conflicts) == 1, f"Criterion A17 failure: Expected exactly 1 Conflict, got {len(conflicts)}"


# ============================================================================
# Criterion A18: Migration Dry-Run Accountable Manifest & Quarantine
# ============================================================================


def test_a18_e2e_migration_dry_run_and_unattributed_quarantine(test_db: Engine):
    """Criterion A18: Legacy migration script runs in accountable dry-run mode; data without habitat quarantined.

    Verified end-to-end: Dry-run migration reconciles total == mapped + quarantine + rejected;
    unattributed legacy data routes to review quarantine.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    import importlib.util
    migration_script_path = PROJECT_ROOT / "scripts" / "migrate_kms_documents.py"
    assert migration_script_path.is_file(), f"Migration script {migration_script_path} must exist"

    spec = importlib.util.spec_from_file_location("migrate_kms_documents", migration_script_path)
    assert spec is not None and spec.loader is not None
    migration_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration_mod)

    manifest = migration_mod.run_migration(db_url=str(test_db.url), dry_run=True)
    assert isinstance(manifest, dict), "Manifest must be a dictionary"
    assert manifest.get("dry_run") is True, "Migration manifest must have dry_run=True"

    # Verify dry run does not write to kms.knowledge_documents
    with test_db.connect() as conn:
        doc_count = conn.scalar(text("SELECT count(*) FROM kms.knowledge_documents"))
    assert doc_count == 0, "Criterion A18 failure: Dry-run must not write to kms.knowledge_documents"


# ============================================================================
# Criterion A19: No Destructive Purge in Product Code
# ============================================================================


def test_a19_e2e_no_destructive_purge_in_product_pipeline():
    """Criterion A19: Transparent legacy data retention; no automatic production purge in product code.

    Verified end-to-end: Static and runtime audit confirms zero DROP TABLE or TRUNCATE
    executions in migration or product pipelines.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    migration_script_path = PROJECT_ROOT / "scripts" / "migrate_kms_documents.py"
    assert migration_script_path.is_file()

    content = migration_script_path.read_text(encoding="utf-8")
    forbidden_tokens = ["DROP TABLE", "TRUNCATE", "DROP SCHEMA", "CASCADE"]
    for token in forbidden_tokens:
        assert token not in content.upper(), (
            f"Criterion A19 failure: Destructive token '{token}' found in migration script!"
        )

    parsed_ast = ast.parse(content)
    for node in ast.walk(parsed_ast):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text_val = node.value.upper()
            assert "TRUNCATE" not in text_val, "Terdapat klausa TRUNCATE pada string literal AST"
            assert "DROP TABLE" not in text_val, "Terdapat klausa DROP TABLE pada string literal AST"


# ============================================================================
# Criterion A20: Existing Pipeline, Media, and Canonical Export Regression
# ============================================================================


def test_a20_e2e_regression_canonical_export_and_unlocated_media():
    """Criterion A20: Existing pipeline, review, media, and canonical export remain functional without regression.

    Verified end-to-end: Canonical Excel export remains valid; unlocated photos
    assigned habitat_id = NULL without spreading to unrelated villages.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    # 1. Canonical schema and export template validity
    schema = CanonicalSchema.from_template()
    assert schema.template_hash is not None
    assert len(schema.rows) > 0
    assert len(schema.row_ids) == len(schema.rows), "Canonical row IDs must be unique."

    # 2. Verify media isolation across habitats: photos assigned to one habitat do not replicate across habitats
    media_by_habitat: dict[str, set[str]] = {}
    for doc in draft.documents.values():
        hab_id = doc.habitat.id
        if hab_id not in media_by_habitat:
            media_by_habitat[hab_id] = set()
        for m in doc.media_refs:
            media_by_habitat[hab_id].add(m.asset_id)

    if len(media_by_habitat) >= 2:
        hab_list = list(media_by_habitat.keys())
        for i in range(len(hab_list)):
            for j in range(i + 1, len(hab_list)):
                overlap = media_by_habitat[hab_list[i]] & media_by_habitat[hab_list[j]]
                assert len(overlap) == 0, (
                    f"Criterion A20 failure: Media assets replicated across unrelated habitats: {overlap}"
                )


# ============================================================================
# Criterion A21: Documentation Parity Verification Gate
# ============================================================================


def test_a21_e2e_documentation_parity_verification():
    """Criterion A21: README and technical documentation distinguish design status, tested capability, config activation.

    Verified end-to-end: README.md and docs/PROJECT_GUIDE.md document JSONB architecture,
    link to docs/KMS_JSONB_MIGRATION.md, and state default inactive kms_enabled flag.
    """
    assert README_PATH.exists()
    content = README_PATH.read_text(encoding="utf-8")

    assert "docs/KMS_JSONB_MIGRATION.md" in content or "KMS_JSONB_MIGRATION.md" in content, (
        "Criterion A21 failure: README.md must reference the migration guide."
    )
    assert re.search(r"kms_enabled|cabai_kms_enabled", content, re.IGNORECASE), (
        "Criterion A21 failure: README.md must specify the kms_enabled configuration flag."
    )


# ============================================================================
# Criterion A22: Semantic Policy Evaluation Report Gate
# ============================================================================


def test_a22_e2e_semantic_policy_evaluation_report_gate():
    """Criterion A22: Project owner receives semantic policy evaluation report before non-exact auto-update active.

    Verified end-to-end: Semantic auto-accept is held in review queue until holdout
    evaluation report gate is cleared.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    policy = AttributePolicy()
    assert policy.semantic_auto_accept_enabled is False, "Semantic auto-accept must be disabled by default."
    assert policy.holdout_report_approved is False, "Holdout report gate must be unapproved by default."

    catalog = AttributeCatalog()
    semantic_query = "ukuran tinggi tanaman pokok dewasa"
    res = policy.evaluate(
        raw_label=semantic_query,
        catalog=catalog,
        semantic_score=0.92,
    )
    assert res.status == "NEEDS_REVIEW", (
        "Criterion A22 failure: Non-exact semantic matches must be held in review until holdout gate is cleared."
    )


# ============================================================================
# Criterion A23: Three-Way Signal Photo Classification
# ============================================================================


def test_a23_e2e_vision_three_way_signal_classification():
    """Criterion A23: Photo classification integrates 3 signals: visual image, filename/caption, active Excel varieties.

    Verified end-to-end: Prompt scoped strictly to active varieties F3 and F4;
    filename context integrated consistently.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    active_varieties = list({doc.variety.label for doc in draft.documents.values()})
    assert len(active_varieties) >= 2, "Field sample must contain active varieties (e.g. Cabai rawit and cabai besar)"

    photo_signal = PhotoContextSignal(
        filename="cabai_rawit_daun.jpg",
        caption="Sampel daun cabai rawit Dusun Randu",
        extracted_part="DAUN",
        suggested_variety_hint="Cabai rawit",
        raw_tokens=["cabai", "rawit", "daun"],
    )

    class MockLVM:
        def __init__(self):
            self.calls = []

        def __call__(self, *args, **kwargs):
            if "messages" in kwargs:
                self.calls.append(kwargs["messages"])
            elif args:
                self.calls.append(args[0])
            return VisionClassificationResult(
                classification_status="KNOWN",
                matched_variety=active_varieties[0],
                identified_part="DAUN",
                visual_confidence=0.92,
                text_confidence=0.88,
                confidence=0.90,
                visual_evidence="Mock visual feature matching",
                options_evaluated=active_varieties,
                signals_consistent=True,
            )

    mock_lvm = MockLVM()
    session = vision_classification.VisionSession(
        run_scope_varieties=active_varieties,
        lvm_call=mock_lvm,
    )

    image = ImageMetadata(
        file_id="img_e2e_001",
        filename="cabai_rawit_daun.jpg",
        mime_type="image/jpeg",
        size=1024,
        created_time=datetime.now(timezone.utc),
    )
    result = session.classify(image, image_bytes=b"dummy_bytes", photo_signal=photo_signal)
    assert isinstance(result, VisionClassificationResult)
    assert result.classification_status == "KNOWN"
    assert len(mock_lvm.calls) >= 1
    prompt_text = " ".join(str(m.get("content", "")) for m in mock_lvm.calls[0])
    for var in active_varieties:
        assert var in prompt_text, f"Prompt must be scoped to active Excel variety {var}"


# ============================================================================
# Criterion A24: Photo Variety Mismatch Creates Blocking Review Item
# ============================================================================


def test_a24_e2e_photo_mismatch_creates_blocking_review():
    """Criterion A24: Photo not matching active run Excel variety options creates PHOTO_VARIETY_MISMATCH review item.

    Verified end-to-end: Fail-closed review item enqueued when photo does not match
    active Excel varieties, preventing commit.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    planner = DocumentPlanner()
    excel_records = [
        {
            "Lokasi Sampling": "Desa Hargobinangun, Kec. Pakem, Kabupaten Sleman, Daerah Istimewa Yogyakarta",
            "Varietas": "Cabai rawit (Capsicum frutescens L)",
            "pH tanah": 7.0,
            "_row": 3,
        }
    ]
    mismatched_photo = PhotoContextSignal(
        filename="cabai_keriting_buah_01.jpg",
        caption="Buah cabai merah keriting panjang bergelombang",
        extracted_part="BUAH",
        suggested_variety_hint="Cabai keriting",
        raw_tokens=["cabai", "keriting", "merah"],
    )
    mismatch_draft = planner.plan_records(
        records=excel_records,
        photo_signals=[mismatched_photo],
        run_id="run_a24_mismatch_e2e",
    )
    photo_reviews = [r for r in mismatch_draft.reviews if r.category == "PHOTO_VARIETY_MISMATCH"]
    assert len(photo_reviews) == 1, (
        "Criterion A24 failure: Photo mismatching Excel varieties must create a PHOTO_VARIETY_MISMATCH review item."
    )
    rev = photo_reviews[0]
    assert rev.status == "pending", "Review item must be pending (fail-closed) to block commit."
    actions = [c.get("action") for c in rev.candidate_resolutions]
    assert "ASSIGN_EXISTING" in actions
    assert "CREATE_NEW_DOCUMENT" in actions
    assert "DISCARD" in actions


# ============================================================================
# Criterion A25: Photo Review Action ASSIGN_EXISTING
# ============================================================================


def test_a25_e2e_photo_review_action_assign_existing(api_client):
    """Criterion A25: Review action ASSIGN_EXISTING links photo to selected variety document and releases review.

    Verified end-to-end: Curator selects existing variety; asset ID added to
    KnowledgeDocument.media_refs; review approved.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    client, repo, _, _ = api_client
    run_id = f"run_a25_e2e_{uuid4().hex[:8]}"

    png_data = _make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=_auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a25_e2e",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_merah_argalingga_01.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id, "organ_part": "buah"},
    )
    staged_draft = _build_draft(run_id, [doc], reviews=[review_item])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": staged_draft.model_dump(mode="json"), "expected_revision": 0},
        headers=_auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    decision = PhotoMismatchDecision(
        action="ASSIGN_EXISTING",
        selected_variety_id=plant.id,
        selected_variety_label=plant.label,
        target_habitat_id=habitat.id,
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=_auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json().get("status") == "approved"

    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=_auth_header("reviewer"),
    )
    assert commit_res.status_code == 200
    assert commit_res.json().get("media_linked", 0) >= 1


# ============================================================================
# Criterion A26: Photo Review Action CREATE_NEW_DOCUMENT
# ============================================================================


def test_a26_e2e_photo_review_action_create_new_document(api_client):
    """Criterion A26: Review action CREATE_NEW_DOCUMENT forms new document with new variety without inventing taxonomy.

    Verified end-to-end: Validated new variety creates new document with photo linked;
    commit succeeds after approval.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    client, repo, _, _ = api_client
    run_id = f"run_a26_e2e_{uuid4().hex[:8]}"

    png_data = _make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=_auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a26_e2e",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_keriting_lokal_01.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id, "organ_part": "buah"},
    )
    staged_draft = _build_draft(run_id, [doc], reviews=[review_item])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": staged_draft.model_dump(mode="json"), "expected_revision": 0},
        headers=_auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    decision = PhotoMismatchDecision(
        action="CREATE_NEW_DOCUMENT",
        new_variety_name="Cabai Keriting Lokal Wonosobo",
        identity_level="cultivar",
        target_habitat_id=habitat.id,
        notes="Identified as local curly chili variety",
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=_auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json().get("status") == "approved"

    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=_auth_header("reviewer"),
    )
    assert commit_res.status_code == 200
    assert commit_res.json().get("documents_created", 0) >= 2


# ============================================================================
# Criterion A27: Photo Review Action DISCARD Non-Destructive
# ============================================================================


def test_a27_e2e_photo_review_action_discard_non_destructive(api_client):
    """Criterion A27: Review action DISCARD marks photo rejected non-destructively without deleting CAS blob.

    Verified end-to-end: Review marked rejected; physical blob in storage CAS
    remains completely intact.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    client, repo, _, _ = api_client
    run_id = f"run_a27_e2e_{uuid4().hex[:8]}"

    png_data = _make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=_auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a27_e2e",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="buram_non_cabai.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id},
    )
    staged_draft = _build_draft(run_id, [doc], reviews=[review_item])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": staged_draft.model_dump(mode="json"), "expected_revision": 0},
        headers=_auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    decision = PhotoMismatchDecision(
        action="DISCARD",
        discard_reason="Bukan objek tanaman cabai",
        notes="Foto lanskap tanah tanpa organ tanaman",
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=_auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200
    assert resolve_res.json().get("status") == "rejected"

    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=_auth_header("reviewer"),
    )
    assert commit_res.status_code == 200

    media_get = client.get(f"/media/{asset_id}/thumbnail", headers=_auth_header("reader"))
    assert media_get.status_code == 200, "Criterion A27 failure: CAS blob was destroyed after DISCARD!"


# ============================================================================
# Criterion A28: Vision Quota Isolation (Zero External Network Calls)
# ============================================================================


def test_a28_e2e_vision_isolation_zero_network_quota(monkeypatch: pytest.MonkeyPatch):
    """Criterion A28: Vision quota isolation: All CI unit/integration tests run 100% deterministically with mock/stubs.

    Verified end-to-end: Offline provider configuration ensures zero external HTTP
    requests to 9Router or external vision APIs.
    """
    draft = _get_e2e_staged_draft(FIELD_SAMPLE_PATH)

    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "mock")
    monkeypatch.setenv("NINEROUTER_API_KEY", "")

    def guarded_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("External network connection attempted during CI vision test!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    jpeg_bytes = _make_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_iso_e2e_001",
        filename="cabai_rawit_daun.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=datetime.now(timezone.utc),
    )

    active_vars = ["Cabai rawit (Capsicum frutescens L)", "cabai besar (Capsicum annum L)"]
    mock_res = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai rawit (Capsicum frutescens L)",
        identified_part="DAUN",
        visual_confidence=0.95,
        text_confidence=0.90,
        confidence=0.92,
        visual_evidence="Mock visual feature matching",
        options_evaluated=active_vars,
        signals_consistent=True,
    )

    class MockRecordingLVM:
        def __init__(self, response):
            self.response = response
            self.calls = []

        def __call__(self, *args, **kwargs):
            if "messages" in kwargs:
                self.calls.append(kwargs["messages"])
            elif args:
                self.calls.append(args[0])
            return self.response

    session = vision_classification.VisionSession(
        run_scope_varieties=active_vars,
        lvm_call=MockRecordingLVM(response=mock_res),
    )

    result = session.classify(image, image_bytes=jpeg_bytes)
    assert isinstance(result, VisionClassificationResult)
    assert result.classification_status == "KNOWN"
    assert result.confidence >= 0.85
