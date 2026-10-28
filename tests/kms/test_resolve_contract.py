"""Unit and integration contract tests for L1: API review resolution unwrapping and bridge contract (C-01..C-07).

Tests:
C-01: Flat decision body accepted; repository receives flat decision.
C-02: Nested {"decision": {...}} body accepted; repository receives flat decision.
C-03: Malformed payload {"decision": {...}, "x": 1} rejected with HTTP 422.
C-04: Bridge UI->API via resolve_review_item_v2 for KEEP_EXISTING, APPLY_INCOMING, REVISE
      on OVERWRITE_BLOCKED / UNIT_MISMATCH -> draft status and document updated appropriately.
C-05: Bridge UI->API via photo_review functions:
      - resolve_photo_assign_existing links media
      - resolve_photo_create_new_document creates document
      - resolve_photo_discard marks media discarded
C-06: Decision payload without action AND without status rejected with HTTP 4xx, item remains pending.
C-07: Generic decision {"status": "approved"} for other categories (e.g. NEW_ATTRIBUTE) continues to work.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from typing import Any
import pytest
from starlette.testclient import TestClient

from src.kms_api.app import create_app
from src.integrations.photo_review import (
    resolve_photo_assign_existing,
    resolve_photo_create_new_document,
    resolve_photo_discard,
)
from src.integrations.streamlit_commit import resolve_review_item_v2
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_contracts import (
    AttributeValue,
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
from src.storage.identity_resolution import AdministrativeRegistry
from src.storage.image_storage import LocalCAS
from src.storage.migrate import migrate
from src.storage.repository import KmsRepository

pytestmark = pytest.mark.integration


class FakeUIClient:
    """Fake client implementing KmsClient.request contract over starlette TestClient."""

    def __init__(self, test_client: TestClient, token: str):
        self._client = test_client
        self._token = token

    def request(self, method: str, path: str, **kwargs) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {self._token}"
        resp = self._client.request(method, path, headers=headers, **kwargs)
        if resp.status_code >= 400:
            from src.storage.errors import Conflict, InvalidState

            try:
                detail = resp.json().get("detail", "Error")
            except Exception:
                detail = resp.text
            if resp.status_code == 409:
                raise Conflict(detail)
            raise InvalidState(f"HTTP {resp.status_code}: {detail}")
        if resp.headers.get("content-type", "").startswith("application/json"):
            return resp.json()
        return resp.content


@pytest.fixture
def api_client(tmp_path):
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured")
    admin_url = os.getenv("TEST_DATABASE_ADMIN_URL", url)
    migrate(admin_url)

    tokens = {
        "r" * 40: {"subject": "reader-1", "role": "reader"},
        "w" * 40: {"subject": "reviewer-1", "role": "reviewer"},
        "c" * 40: {"subject": "curator-1", "role": "curator"},
    }
    media_dir = tmp_path / "media_test_resolve"
    media_dir.mkdir(parents=True, exist_ok=True)
    settings = Settings(
        _env_file=None,
        database_url=url,
        database_admin_url=admin_url,
        kms_tokens_json=json.dumps(tokens),
        media_storage_path=media_dir,
        media_min_free_bytes=0,
    )
    engine = make_engine(settings)
    repo = KmsRepository(engine)
    blob_store = LocalCAS(media_dir, min_free_bytes=0)
    app = create_app(settings, repository=repo, blob_store=blob_store)
    with TestClient(app) as client:
        yield client, settings


def _setup_staged_run_with_reviews(
    engine,
    run_id: str,
    reviews: list[DocumentReviewItem],
    *,
    doc: KnowledgeDocument | None = None,
) -> tuple[DocumentRepository, KnowledgeDocument]:
    kms_repo = KmsRepository(engine)
    doc_repo = DocumentRepository(engine)

    import hashlib
    sha = hashlib.sha256(run_id.encode()).hexdigest()
    kms_repo.register_source(sha, f"cas:///sources/{run_id}.xlsx", 1000, actor="curator-1")

    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    plant = PlantIdentity(id="plant_c", label="Cabai Rawit", identity_level="cultivar")
    doc_key = f"{plant.id}:{habitat.id}"
    if doc is None:
        doc = KnowledgeDocument(
            schema_version="kms-document-v1",
            variety=plant,
            habitat=habitat,
            sampling_locations=[SamplingLocationDetail(location_ref="loc_01", raw_address="Sleman")],
            attributes={
                "attr_tinggi_tanaman": AttributeValue(
                    label="tinggi tanaman",
                    value=80.0,
                    value_type="number",
                    unit="cm",
                    resolution="HUMAN_REVIEW",
                    current_source=CurrentSourceReference(
                        source_ref="s.xlsx", sheet="S1", row=1, cell="A1", location_ref="loc_01"
                    ),
                )
            },
            media_refs=[],
            updated_by_run=run_id,
            doc_id=doc_key,
        )

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
        documents={doc_key: doc},
        reviews=reviews,
        base_versions={doc_key: 0},
    )
    doc_repo.stage(draft, expected_revision=0, actor="curator-1")
    return doc_repo, doc


def test_c01_flat_decision_body_accepted(api_client):
    """C-01: Flat decision body accepted; repository receives flat decision."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c01_{uuid.uuid4().hex[:6]}"

    rev = DocumentReviewItem(
        item_id="rev_c01",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    _setup_staged_run_with_reviews(engine, run_id, [rev])

    # Send flat decision body
    resp = client.post(
        f"/runs/v2/{run_id}/reviews/rev_c01/resolve",
        headers={"Authorization": "Bearer " + "c" * 40},
        json={"action": "KEEP_EXISTING", "notes": "Flat body decision"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"]["action"] == "KEEP_EXISTING"


def test_c02_nested_decision_body_accepted(api_client):
    """C-02: Nested {"decision": {...}} body accepted; repository receives flat decision."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c02_{uuid.uuid4().hex[:6]}"

    rev = DocumentReviewItem(
        item_id="rev_c02",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    _setup_staged_run_with_reviews(engine, run_id, [rev])

    # Send nested decision body
    resp = client.post(
        f"/runs/v2/{run_id}/reviews/rev_c02/resolve",
        headers={"Authorization": "Bearer " + "c" * 40},
        json={"decision": {"action": "KEEP_EXISTING", "notes": "Nested body decision"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "rejected"
    assert data["decision"]["action"] == "KEEP_EXISTING"


def test_c03_malformed_mixed_decision_body_rejected_422(api_client):
    """C-03: Malformed payload {"decision": {...}, "x": 1} rejected with HTTP 422."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c03_{uuid.uuid4().hex[:6]}"

    rev = DocumentReviewItem(
        item_id="rev_c03",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={"attribute_id": "attr_tinggi_tanaman"},
    )
    _setup_staged_run_with_reviews(engine, run_id, [rev])

    # Mixed keys: 'decision' and 'x'
    resp = client.post(
        f"/runs/v2/{run_id}/reviews/rev_c03/resolve",
        headers={"Authorization": "Bearer " + "c" * 40},
        json={"decision": {"action": "KEEP_EXISTING"}, "x": 1},
    )
    assert resp.status_code == 422


def test_c04_bridge_streamlit_resolve_review_item_v2(api_client):
    """C-04: Bridge resolve_review_item_v2 for KEEP_EXISTING, APPLY_INCOMING, and REVISE updates draft."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c04_{uuid.uuid4().hex[:6]}"

    rev_keep = DocumentReviewItem(
        item_id="rev_keep",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    rev_apply = DocumentReviewItem(
        item_id="rev_apply",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 3",
        raw_values=[80.0, "tinggi_sekali"],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": "tinggi_sekali",
            "old_unit": "cm",
            "new_unit": None,
            "new_attribute": {
                "label": "tinggi tanaman",
                "value": "tinggi_sekali",
                "value_type": "text",
                "unit": None,
                "resolution": "HUMAN_REVIEW",
                "current_source": {
                    "source_ref": "s.xlsx",
                    "sheet": "S1",
                    "row": 3,
                    "cell": "A3",
                    "location_ref": "loc_01",
                },
            },
        },
    )
    rev_revise = DocumentReviewItem(
        item_id="rev_revise",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="row 4",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
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
                "current_source": {
                    "source_ref": "s.xlsx",
                    "sheet": "S1",
                    "row": 1,
                    "cell": "A1",
                    "location_ref": "loc_01",
                },
            },
        },
    )
    doc_repo, _ = _setup_staged_run_with_reviews(engine, run_id, [rev_keep, rev_apply, rev_revise])

    bridge_client = FakeUIClient(client, "c" * 40)

    # 1. KEEP_EXISTING via resolve_review_item_v2
    res_k = resolve_review_item_v2(
        run_id, "rev_keep", {"action": "KEEP_EXISTING"}, client=bridge_client
    )
    assert res_k["status"] == "rejected"

    # 2. APPLY_INCOMING via resolve_review_item_v2
    res_a = resolve_review_item_v2(
        run_id, "rev_apply", {"action": "APPLY_INCOMING", "reason": "Curator verified qualitative value"}, client=bridge_client
    )
    assert res_a["status"] == "approved"

    # 3. REVISE via resolve_review_item_v2
    res_r = resolve_review_item_v2(
        run_id, "rev_revise", {"action": "REVISE", "corrected_value": 85.0, "corrected_unit": "cm", "reason": "Fixed typo kg->cm"}, client=bridge_client
    )
    assert res_r["status"] == "revised"

    # Check updated draft state
    run = doc_repo.get_run(run_id)
    reviews = {r["item_id"]: r for r in run["draft"]["reviews"]}
    assert reviews["rev_keep"]["status"] == "rejected"
    assert reviews["rev_apply"]["status"] == "approved"
    assert reviews["rev_revise"]["status"] == "revised"


def test_c05_bridge_photo_review_functions(api_client):
    """C-05: Bridge photo review functions (ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD) via KMS API."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c05_{uuid.uuid4().hex[:6]}"

    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    plant = PlantIdentity(id="plant_c", label="Cabai Rawit", identity_level="cultivar")
    doc_key = f"{plant.id}:{habitat.id}"

    aid1 = "1" * 64
    aid2 = "2" * 64
    aid3 = "3" * 64

    rev_p1 = DocumentReviewItem(
        item_id="rev_p1",
        category="PHOTO_VARIETY_MISMATCH",
        source_label="foto_cabe_daun.png",
        source_context="drive",
        raw_values=[aid1],
        status="pending",
        target_document_key=doc_key,
        payload={"asset_id": aid1, "organ_part": "daun", "caption": "Daun cabai"},
    )
    rev_p2 = DocumentReviewItem(
        item_id="rev_p2",
        category="PHOTO_VARIETY_MISMATCH",
        source_label="foto_cabe_baru.png",
        source_context="drive",
        raw_values=[aid2],
        status="pending",
        target_document_key=doc_key,
        payload={"asset_id": aid2, "organ_part": "buah", "caption": "Cabai varietas baru"},
    )
    rev_p3 = DocumentReviewItem(
        item_id="rev_p3",
        category="PHOTO_VARIETY_MISMATCH",
        source_label="foto_buruk.png",
        source_context="drive",
        raw_values=[aid3],
        status="pending",
        target_document_key=doc_key,
        payload={"asset_id": aid3, "organ_part": "bunga", "caption": "Blurry photo"},
    )

    doc_initial = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[SamplingLocationDetail(location_ref="loc_01", raw_address="Sleman")],
        attributes={},
        media_refs=[
            MediaReference(
                asset_id=aid3,
                organ_part="bunga",
                source_filename="foto_buruk.png",
                provenance_run_id=run_id,
                assigned_via="AUTO_ACCEPT",
                resolution_status="linked",
            )
        ],
        updated_by_run=run_id,
        doc_id=doc_key,
    )
    doc_repo, _ = _setup_staged_run_with_reviews(
        engine, run_id, [rev_p1, rev_p2, rev_p3], doc=doc_initial
    )

    bridge_client = FakeUIClient(client, "c" * 40)

    # 1. ASSIGN_EXISTING
    r1 = resolve_photo_assign_existing(
        run_id, "rev_p1", selected_variety_id="plant_c", target_habitat_id=habitat.id, client=bridge_client
    )
    assert r1["status"] == "approved"

    # 2. CREATE_NEW_DOCUMENT
    r2 = resolve_photo_create_new_document(
        run_id, "rev_p2", new_variety_name="Cabai Hibrida C05", target_habitat_id=habitat.id, client=bridge_client
    )
    assert r2["status"] == "approved"

    # 3. DISCARD
    r3 = resolve_photo_discard(run_id, "rev_p3", discard_reason="Kualitas buruk", client=bridge_client)
    assert r3["status"] == "rejected"

    # Verify draft mutations
    run = doc_repo.get_run(run_id)
    draft = DocumentDraft.model_validate(run["draft"])
    # Media was linked to existing document
    assert any(m.asset_id == aid1 for m in draft.documents[doc_key].media_refs)
    # Media 003 marked discarded
    assert any(m.asset_id == aid3 and m.resolution_status == "discarded" for m in draft.documents[doc_key].media_refs)
    # New document was created
    assert len(draft.documents) >= 2


def test_c06_decision_without_action_and_without_status_rejected(api_client):
    """C-06: Decision payload without action AND without status rejected with HTTP 4xx, item remains pending."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c06_{uuid.uuid4().hex[:6]}"

    rev = DocumentReviewItem(
        item_id="rev_c06",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={"attribute_id": "attr_tinggi_tanaman"},
    )
    doc_repo, _ = _setup_staged_run_with_reviews(engine, run_id, [rev])

    # Send decision payload with neither 'action' nor 'status'
    resp = client.post(
        f"/runs/v2/{run_id}/reviews/rev_c06/resolve",
        headers={"Authorization": "Bearer " + "c" * 40},
        json={"notes": "No action or status provided"},
    )
    assert resp.status_code in (400, 422)

    # Item must remain pending
    run = doc_repo.get_run(run_id)
    item = next(r for r in run["draft"]["reviews"] if r["item_id"] == "rev_c06")
    assert item["status"] == "pending"


def test_c07_generic_status_approved_for_other_categories_works(api_client):
    """C-07: Generic decision {"status": "approved"} for other categories (e.g. NEW_ATTRIBUTE) continues to work."""
    client, settings = api_client
    url = os.getenv("TEST_DATABASE_URL")
    engine = make_engine(Settings(_env_file=None, database_url=url))
    run_id = f"run_c07_{uuid.uuid4().hex[:6]}"

    rev = DocumentReviewItem(
        item_id="rev_c07",
        category="NEW_ATTRIBUTE",
        source_label="warna mahkota",
        source_context="row 5",
        raw_values=["putih bersih"],
        status="pending",
        target_document_key="plant_c:hab_c",
        payload={"attribute_id": "attr_warna_mahkota"},
    )
    doc_repo, _ = _setup_staged_run_with_reviews(engine, run_id, [rev])

    resp = client.post(
        f"/runs/v2/{run_id}/reviews/rev_c07/resolve",
        headers={"Authorization": "Bearer " + "c" * 40},
        json={"status": "approved", "notes": "Approved new attribute"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "approved"
