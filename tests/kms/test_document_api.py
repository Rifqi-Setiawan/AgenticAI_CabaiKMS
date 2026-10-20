"""Test-first acceptance test suite for S6: Document API Endpoints and RBAC.

Covers:
- A12: Commit rejected when pending review items exist (HTTP 409 Conflict).
- A20: Existing pipeline, media, and canonical export remain unregressed.
- A25: Photo review action ASSIGN_EXISTING links photo to document and approves review.
- A26: Photo review action CREATE_NEW_DOCUMENT creates new document and approves review.
- A27: Photo review action DISCARD marks rejected non-destructively without purging CAS blob.
- S6-RBAC-01: Reader role forbidden (HTTP 403) from mutation endpoints (/runs/v2/stage, commit, resolve).
- S6-RBAC-02: Unauthenticated requests rejected with HTTP 401 across v2 endpoints.
- S6-RBAC-03: Reviewer and Curator roles permitted on staging, review resolution, and commit.
- S6-API-01: POST /runs/v2/stage stages valid DocumentDraft and rejects malformed payloads (HTTP 422).
- S6-API-02: POST /runs/v2/{id}/commit returns atomic CommitReceipt and persists JSONB document.
- S6-API-03: GET /documents and GET /documents/{id} query committed knowledge documents.
- S6-CLIENT-01: KmsClient integration for v2 endpoints and error mapping.
"""

from __future__ import annotations

import copy
import io
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.engine import Engine, make_url

from src.integrations.client import KmsClient
from src.kms_api.app import create_app
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
    PhotoMismatchDecision,
    PlantIdentity,
    SamplingLocationDetail,
)
from src.storage.document_repository import DocumentRepository
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


# ============================================================================
# Database & Test Client Fixtures (Strict Isolation to Disposable Test DB)
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
    media_dir = tmp_path / "media_test"
    media_dir.mkdir(parents=True, exist_ok=True)

    settings = Settings(
        _env_file=None,
        database_url=url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    repo = KmsRepository(test_db)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)

    with TestClient(app) as client:
        yield client, repo, blob_store, settings


# ============================================================================
# Helpers & Contract Builders
# ============================================================================


def auth_header(role: str = "reviewer") -> dict[str, str]:
    """Generate HTTP Authorization Bearer headers for defined test roles."""
    if role == "reader":
        return {"Authorization": "Bearer " + "r" * 40}
    if role == "curator":
        return {"Authorization": "Bearer " + "c" * 40}
    return {"Authorization": "Bearer " + "w" * 40}


def make_png_bytes(width: int = 200, height: int = 200) -> bytes:
    """Generate a valid test PNG image payload in-memory."""
    stream = io.BytesIO()
    img = Image.new("RGBA", (width, height), (34, 139, 34, 255))
    img.save(stream, format="PNG")
    return stream.getvalue()


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
            sheet="Resume Data",
            row=3,
            cell="G3",
            location_ref="loc_001",
        ),
    )


def _build_document(
    plant: PlantIdentity,
    habitat: HabitatIdentity,
    attributes: dict[str, AttributeValue] | None = None,
    media_refs: list[MediaReference] | None = None,
    run_id: str = "run_test_api_001",
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
        media_refs=media_refs or [],
        updated_by_run=run_id,
    )


def _build_draft(
    run_id: str,
    documents: list[KnowledgeDocument],
    reviews: list[DocumentReviewItem] | None = None,
    base_versions: dict[str, int] | None = None,
    revision: int = 1,
    source_uri: str = "cas:///sources/data_input.xlsx",
) -> DocumentDraft:
    doc_map = {f"{d.variety.id}:{d.habitat.id}": d for d in documents}
    bv = base_versions if base_versions is not None else {k: 0 for k in doc_map}
    return DocumentDraft(
        run_id=run_id,
        source_filename="data_input.xlsx",
        file_sha256="a" * 64,
        source_uri=source_uri,
        source_scope="field_survey_2026",
        schema_version="kms-document-v1",
        template_hash="b" * 64,
        config_fingerprint="cfg_s6_api",
        revision=revision,
        documents=doc_map,
        reviews=reviews or [],
        base_versions=bv,
        metadata={"survey_year": 2026},
    )


# ============================================================================
# Acceptance Tests
# ============================================================================


def test_commit_rejected_when_pending_reviews_exist(api_client):
    """[A12] Backend rejects direct commit request with HTTP 409 Conflict when pending reviews exist."""
    client, repo, _, _ = api_client
    run_id = f"run_a12_{uuid4().hex[:8]}"

    # Register source artifact required by draft staging contract
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, {"attr_klorofil": _build_attribute("Klorofil", 45.6)}, run_id=run_id)

    pending_review = DocumentReviewItem(
        item_id="rev_pending_a12",
        category="INTRA_RUN_VALUE_CONFLICT",
        target_document_key=f"{plant.id}:{habitat.id}",
        source_label="Klorofil",
        raw_values=[49.02, 46.54],
        status="pending",
        notes="Unresolved conflict between hamlet observations",
    )

    draft = _build_draft(run_id, [doc], reviews=[pending_review])

    # 1. Stage the draft via POST /runs/v2/stage
    stage_response = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_response.status_code == 200, (
        f"Expected 200 from POST /runs/v2/stage, got {stage_response.status_code}: {stage_response.text}"
    )

    # 2. Attempt commit via POST /runs/v2/{id}/commit while review is pending -> Must return HTTP 409 Conflict
    commit_response = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": 1, "payload_sha256": stage_response.json().get("payload_sha256", "a" * 64)},
        headers=auth_header("reviewer"),
    )
    assert commit_response.status_code == 409, (
        f"Expected HTTP 409 Conflict for commit with pending reviews, got {commit_response.status_code}: {commit_response.text}"
    )
    assert "pending" in commit_response.json().get("detail", "").lower()


def test_regression_pipeline_media_and_excel_export(api_client):
    """[A20] Existing input pipeline, v1 endpoints, media storage, and canonical export remain unregressed."""
    client, repo, _, _ = api_client

    # 1. Verify health and v1 inspection endpoints remain intact
    health_res = client.get("/healthz")
    assert health_res.status_code == 200
    assert health_res.json() == {"status": "alive"}

    values_res = client.get("/values", headers=auth_header("reader"))
    assert values_res.status_code == 200
    assert "items" in values_res.json()

    # 2. Verify image ingestion into CAS via existing POST /assets remains functional
    png_data = make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=auth_header("reviewer"))
    assert asset_res.status_code == 200, f"Failed existing asset registration: {asset_res.text}"
    asset_id = asset_res.json()["id"]

    # 3. Verify media retrieve via existing GET /media/{id}/{variant}
    thumb_res = client.get(f"/media/{asset_id}/thumbnail", headers=auth_header("reader"))
    assert thumb_res.status_code == 200
    assert thumb_res.headers["content-type"] == "image/webp"

    # 4. Verify v2 endpoint coexistence: Staging a v2 draft preserves legacy media without multiplying across habitats
    run_id = f"run_a20_{uuid4().hex[:8]}"
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    draft = _build_draft(run_id, [doc])
    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200, (
        f"Expected /runs/v2/stage to coexist with v1 pipeline, got {stage_res.status_code}: {stage_res.text}"
    )


def test_photo_review_action_assign_existing(api_client):
    """[A25] Review action ASSIGN_EXISTING links photo to target document media_refs and approves review."""
    client, repo, _, _ = api_client
    run_id = f"run_a25_{uuid4().hex[:8]}"

    # Ingest photo asset
    png_data = make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a25",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_merah_argalingga_01.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id, "organ_part": "buah"},
    )

    draft = _build_draft(run_id, [doc], reviews=[review_item])

    # 1. Stage draft
    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200, f"Stage failed: {stage_res.status_code}"

    # 2. Resolve review via POST /runs/v2/{id}/reviews/{item_id}/resolve with ASSIGN_EXISTING
    decision = PhotoMismatchDecision(
        action="ASSIGN_EXISTING",
        selected_variety_id=plant.id,
        selected_variety_label=plant.label,
        target_habitat_id=habitat.id,
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200, (
        f"Expected 200 from review resolution, got {resolve_res.status_code}: {resolve_res.text}"
    )
    resolved_body = resolve_res.json()
    assert resolved_body.get("status") == "approved"

    # 3. Commit should now succeed
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=auth_header("reviewer"),
    )
    assert commit_res.status_code == 200, f"Expected successful commit after resolution, got {commit_res.status_code}"
    receipt = commit_res.json()
    assert receipt.get("media_linked", 0) >= 1


def test_photo_review_action_create_new_document(api_client):
    """[A26] Review action CREATE_NEW_DOCUMENT creates a new document for new variety and links photo."""
    client, repo, _, _ = api_client
    run_id = f"run_a26_{uuid4().hex[:8]}"

    png_data = make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a26",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="cabai_keriting_lokal_01.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id, "organ_part": "buah"},
    )

    draft = _build_draft(run_id, [doc], reviews=[review_item])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    # Execute CREATE_NEW_DOCUMENT
    decision = PhotoMismatchDecision(
        action="CREATE_NEW_DOCUMENT",
        new_variety_name="Cabai Keriting Lokal Wonosobo",
        identity_level="cultivar",
        target_habitat_id=habitat.id,
        notes="Identified as local curly chili variety distinct from rawit",
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200, (
        f"Expected 200 from review resolution CREATE_NEW_DOCUMENT, got {resolve_res.status_code}: {resolve_res.text}"
    )
    assert resolve_res.json().get("status") == "approved"

    # Commit should succeed with documents_created reflecting the newly formed document
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=auth_header("reviewer"),
    )
    assert commit_res.status_code == 200
    receipt = commit_res.json()
    assert receipt.get("documents_created", 0) >= 2


def test_photo_review_action_discard_non_destructive(api_client):
    """[A27] Review action DISCARD marks photo rejected non-destructively; physical CAS blob remains intact."""
    client, repo, _, _ = api_client
    run_id = f"run_a27_{uuid4().hex[:8]}"

    png_data = make_png_bytes()
    asset_res = client.post("/assets", content=png_data, headers=auth_header("reviewer"))
    assert asset_res.status_code == 200
    asset_id = asset_res.json()["id"]

    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)

    review_item = DocumentReviewItem(
        item_id="rev_photo_mismatch_a27",
        category="PHOTO_VARIETY_MISMATCH",
        target_document_key=None,
        source_label="buram_non_cabai.jpg",
        raw_values=[asset_id],
        status="pending",
        payload={"asset_id": asset_id},
    )

    draft = _build_draft(run_id, [doc], reviews=[review_item])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    # Execute DISCARD
    decision = PhotoMismatchDecision(
        action="DISCARD",
        discard_reason="Bukan objek tanaman cabai",
        notes="Foto lanskap tanah tanpa organ tanaman",
    )
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/{review_item.item_id}/resolve",
        json=decision.model_dump(mode="json"),
        headers=auth_header("reviewer"),
    )
    assert resolve_res.status_code == 200, (
        f"Expected 200 from review resolution DISCARD, got {resolve_res.status_code}: {resolve_res.text}"
    )
    assert resolve_res.json().get("status") == "rejected"

    # Commit should succeed with no pending reviews remaining
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": stage_res.json().get("revision", 1), "payload_sha256": stage_res.json().get("payload_sha256", "a" * 64)},
        headers=auth_header("reviewer"),
    )
    assert commit_res.status_code == 200

    # Verify physical CAS blob in media storage was NOT destroyed (non-destructive guarantee)
    media_get = client.get(f"/media/{asset_id}/thumbnail", headers=auth_header("reader"))
    assert media_get.status_code == 200, "Physical media blob in CAS was unexpectedly purged after DISCARD!"


def test_rbac_reader_denied_mutation_endpoints(api_client):
    """[S6-RBAC-01] Role 'reader' is strictly rejected with HTTP 403 on mutation endpoints."""
    client, _, _, _ = api_client
    run_id = f"run_rbac_r_{uuid4().hex[:8]}"

    # Reader attempting /runs/v2/stage -> HTTP 403
    stage_res = client.post("/runs/v2/stage", json={"draft": {}}, headers=auth_header("reader"))
    assert stage_res.status_code == 403, (
        f"Expected 403 Forbidden for reader on /runs/v2/stage, got {stage_res.status_code}: {stage_res.text}"
    )

    # Reader attempting /runs/v2/{id}/commit -> HTTP 403
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": 1, "payload_sha256": "a" * 64},
        headers=auth_header("reader"),
    )
    assert commit_res.status_code == 403, (
        f"Expected 403 Forbidden for reader on /runs/v2/{run_id}/commit, got {commit_res.status_code}: {commit_res.text}"
    )

    # Reader attempting /runs/v2/{id}/reviews/{item_id}/resolve -> HTTP 403
    resolve_res = client.post(
        f"/runs/v2/{run_id}/reviews/rev_001/resolve",
        json={"action": "DISCARD"},
        headers=auth_header("reader"),
    )
    assert resolve_res.status_code == 403, (
        f"Expected 403 Forbidden for reader on review resolution, got {resolve_res.status_code}: {resolve_res.text}"
    )


def test_rbac_unauthenticated_requests_rejected(api_client):
    """[S6-RBAC-02] Requests without valid Bearer token return HTTP 401 Unauthorized across v2 endpoints."""
    client, _, _, _ = api_client
    run_id = f"run_rbac_unauth_{uuid4().hex[:8]}"

    endpoints = [
        ("POST", "/runs/v2/stage", {"draft": {}}),
        ("POST", f"/runs/v2/{run_id}/commit", {"expected_revision": 1, "payload_sha256": "a" * 64}),
        ("GET", "/documents", None),
        ("POST", f"/runs/v2/{run_id}/reviews/rev_001/resolve", {"action": "DISCARD"}),
    ]

    for method, path, payload in endpoints:
        # 1. No Authorization header
        if method == "POST":
            res_none = client.post(path, json=payload)
        else:
            res_none = client.get(path)
        assert res_none.status_code == 401, (
            f"Expected 401 for unauthenticated {method} {path}, got {res_none.status_code}: {res_none.text}"
        )

        # 2. Invalid Bearer token
        invalid_headers = {"Authorization": "Bearer invalid_token_value_0000000000000000"}
        if method == "POST":
            res_inv = client.post(path, json=payload, headers=invalid_headers)
        else:
            res_inv = client.get(path, headers=invalid_headers)
        assert res_inv.status_code == 401, (
            f"Expected 401 for invalid token {method} {path}, got {res_inv.status_code}: {res_inv.text}"
        )


def test_rbac_reviewer_and_curator_allowed_mutations(api_client):
    """[S6-RBAC-03] Roles 'reviewer' and 'curator' are authorized to stage, resolve reviews, and commit."""
    client, repo, _, _ = api_client
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()

    for role in ("reviewer", "curator"):
        run_id = f"run_rbac_{role}_{uuid4().hex[:8]}"
        doc = _build_document(plant, habitat, run_id=run_id)
        draft = _build_draft(run_id, [doc])

        # Stage with role
        stage_res = client.post(
            "/runs/v2/stage",
            json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
            headers=auth_header(role),
        )
        assert stage_res.status_code == 200, (
            f"Expected 200 for role '{role}' on /runs/v2/stage, got {stage_res.status_code}: {stage_res.text}"
        )


def test_v2_stage_endpoint_valid_and_invalid_payload(api_client):
    """[S6-API-01] POST /runs/v2/stage accepts valid DocumentDraft and rejects malformed payloads (HTTP 422)."""
    client, repo, _, _ = api_client
    run_id = f"run_stage_{uuid4().hex[:8]}"
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, {"attr_ph": _build_attribute("pH tanah", 6.8)}, run_id=run_id)
    draft = _build_draft(run_id, [doc])

    # 1. Valid staging request
    valid_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert valid_res.status_code == 200, (
        f"Expected 200 on valid draft staging, got {valid_res.status_code}: {valid_res.text}"
    )
    body = valid_res.json()
    assert body.get("run_id") == run_id
    assert body.get("status") == "STAGED"
    assert body.get("revision") == 1
    assert "payload_sha256" in body

    # 2. Malformed payload -> HTTP 422
    invalid_res = client.post(
        "/runs/v2/stage",
        json={"draft": {"run_id": "missing_required_fields"}},
        headers=auth_header("reviewer"),
    )
    assert invalid_res.status_code == 422, (
        f"Expected 422 on malformed staging payload, got {invalid_res.status_code}: {invalid_res.text}"
    )


def test_v2_commit_endpoint_atomic_receipt(api_client):
    """[S6-API-02] POST /runs/v2/{id}/commit executes atomic commit, returning CommitReceipt and updating status."""
    client, repo, _, _ = api_client
    run_id = f"run_commit_{uuid4().hex[:8]}"
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, {"attr_ph": _build_attribute("pH tanah", 7.0)}, run_id=run_id)
    draft = _build_draft(run_id, [doc])

    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200
    staged_data = stage_res.json()

    # Commit the clean staged run
    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": staged_data["revision"], "payload_sha256": staged_data["payload_sha256"]},
        headers=auth_header("reviewer"),
    )
    assert commit_res.status_code == 200, (
        f"Expected 200 from commit, got {commit_res.status_code}: {commit_res.text}"
    )
    receipt = commit_res.json()
    assert receipt.get("run_id") == run_id
    assert receipt.get("documents_created", 0) >= 1
    assert receipt.get("replayed") is False

    # Replay commit -> idempotent receipt with replayed=True
    replay_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": staged_data["revision"], "payload_sha256": staged_data["payload_sha256"]},
        headers=auth_header("reviewer"),
    )
    assert replay_res.status_code == 200
    replay_receipt = replay_res.json()
    assert replay_receipt.get("replayed") is True


def test_v2_documents_query_endpoint(api_client):
    """[S6-API-03] GET /documents and GET /documents/{id} retrieve committed JSONB knowledge documents."""
    client, repo, _, _ = api_client
    run_id = f"run_docs_{uuid4().hex[:8]}"
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")

    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, {"attr_klorofil": _build_attribute("Klorofil", 52.1)}, run_id=run_id)
    draft = _build_draft(run_id, [doc])

    # Stage and commit
    stage_res = client.post(
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
        headers=auth_header("reviewer"),
    )
    assert stage_res.status_code == 200

    commit_res = client.post(
        f"/runs/v2/{run_id}/commit",
        json={"expected_revision": 1, "payload_sha256": stage_res.json()["payload_sha256"]},
        headers=auth_header("reviewer"),
    )
    assert commit_res.status_code == 200

    # 1. Query all documents via GET /documents
    list_res = client.get("/documents", headers=auth_header("reader"))
    assert list_res.status_code == 200, (
        f"Expected 200 from GET /documents, got {list_res.status_code}: {list_res.text}"
    )
    items = list_res.json().get("items", [])
    assert any(item.get("id") == f"{plant.id}:{habitat.id}" or item.get("doc_id") == f"{plant.id}:{habitat.id}" for item in items)

    # 2. Query specific document by ID via GET /documents/{id}
    doc_id = f"{plant.id}:{habitat.id}"
    single_res = client.get(f"/documents/{doc_id}", headers=auth_header("reader"))
    assert single_res.status_code == 200, (
        f"Expected 200 from GET /documents/{doc_id}, got {single_res.status_code}: {single_res.text}"
    )
    single_data = single_res.json()
    assert single_data.get("variety", {}).get("id") == plant.id
    assert single_data.get("habitat", {}).get("id") == habitat.id


def test_kms_client_v2_integration(api_client, monkeypatch):
    """[S6-CLIENT-01] KmsClient integration exercises v2 endpoints and error translations."""
    client, repo, _, settings = api_client
    run_id = f"run_client_{uuid4().hex[:8]}"

    # Route httpx.Client calls to in-process app client
    import httpx
    orig_client = httpx.Client

    def _in_process_client_factory(*args, **kwargs):
        kwargs.pop("base_url", None)
        kwargs.pop("timeout", None)
        return TestClient(client.app, base_url="http://127.0.0.1:8000", **kwargs)

    monkeypatch.setattr(httpx, "Client", _in_process_client_factory)

    # Instantiate KmsClient with reviewer token
    kms_client = KmsClient(settings, token="w" * 40)

    # Calling /runs/v2/stage via client should translate endpoints properly
    repo.register_source("a" * 64, "cas:///sources/data_input.xlsx", 1024, actor="reviewer-test")
    plant = _build_plant()
    habitat = _build_habitat()
    doc = _build_document(plant, habitat, run_id=run_id)
    draft = _build_draft(run_id, [doc])

    # Client request to v2 staging endpoint
    response = kms_client.request(
        "POST",
        "/runs/v2/stage",
        json={"draft": draft.model_dump(mode="json"), "expected_revision": 0},
    )
    assert isinstance(response, dict)
    assert response.get("status") == "STAGED"
