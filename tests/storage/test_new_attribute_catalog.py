"""Phase 1: curator-approved new attributes become persistent catalog entries.

Covers planner payloads, catalog extensions, REGISTER_NEW / MAP_TO_EXISTING / REJECT resolution,
atomic persistence at commit, reuse by a later run, and guard rails (role, reason, collisions).
Database tests need TEST_DATABASE_URL (PostgreSQL with migrations).
"""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.storage.attribute_policy import (
    AttributeCatalog,
    AttributeDefinition,
    CatalogExtensions,
    apply_catalog_extensions,
    similar_attributes,
    slugify_attribute_key,
)
from src.storage.config import Settings
from src.storage.db import make_engine
from src.storage.document_planner import DocumentPlanner
from src.storage.document_repository import DocumentRepository
from src.storage.errors import Conflict, InvalidState
from src.storage.migrate import migrate

LOC = "Dusun Karang, Desa Hargobinangun, Kec. Pakem, Sleman"


def _records(label: str, values: list[object]) -> list[dict]:
    return [
        {"_row": 2 + i, "_sheet": "Resume Data", "Varietas": "Cabai Rawit",
         "Lokasi Sampling": f"{LOC} (sampling {i + 1})", label: v}
        for i, v in enumerate(values)
    ]


def _novel() -> str:
    return f"Kadar Capsaicin Segar {uuid.uuid4().hex[:6]}"


# ----------------------------------------------------------------------------- no database needed
def test_slug_and_similarity_helpers():
    assert slugify_attribute_key("Kadar Capsaicin Buah (ppm)") == "kadar_capsaicin_buah"
    close = similar_attributes("tinggi tanaman dewasa", AttributeCatalog())
    assert close and close[0]["similarity"] >= 0.72


def test_planner_novel_attribute_items_carry_target_and_value():
    label = _novel()
    draft = DocumentPlanner().plan_records(_records(label, ["1500", "1700"]), run_id="run_na_1")
    items = [r for r in draft.reviews if r.category == "NEW_ATTRIBUTE"]
    assert len(items) == 2
    for item in items:
        assert item.target_document_key in draft.documents
        assert item.payload["raw_value"] in ("1500", "1700")
        assert item.payload["cell"] and item.payload["sheet"] == "Resume Data"
        assert isinstance(item.payload["similar_attributes"], list)


def test_extensions_make_label_known_and_rejections_are_silent():
    known, refused = _novel(), _novel()
    ext = CatalogExtensions(
        attributes=[AttributeDefinition(attribute_id=f"attr_{slugify_attribute_key(known)}",
                                        canonical_key=slugify_attribute_key(known), label=known,
                                        organ="buah", value_type="number", unit="ppm")],
        rejected=[refused.lower()],
    )
    planner = DocumentPlanner(extensions=ext)
    draft = planner.plan_records(_records(known, ["1500"]), run_id="run_na_2")
    assert not [r for r in draft.reviews if r.category == "NEW_ATTRIBUTE"]
    doc = next(iter(draft.documents.values()))
    assert f"attr_{slugify_attribute_key(known)}" in doc.attributes
    draft2 = planner.plan_records(_records(refused, ["x"]), run_id="run_na_3")
    assert not [r for r in draft2.reviews if r.category == "NEW_ATTRIBUTE"]


def test_default_catalog_is_unchanged_without_extensions():
    """Evaluation guard: the template catalog keeps exactly the template rows unless extensions are passed explicitly."""
    from src.schema.canonical import CanonicalSchema

    base = AttributeCatalog()
    rows = len(CanonicalSchema.from_template().rows)
    assert len(base) == rows
    apply_catalog_extensions(base, CatalogExtensions())
    assert len(base) == rows


# ----------------------------------------------------------------------------- database tests
pytestmark_db = pytest.mark.integration


@pytest.fixture
def db() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; PostgreSQL test database required.")
    migrate(os.getenv("TEST_DATABASE_ADMIN_URL", url))
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


def _stage(repo: DocumentRepository, draft, run_id: str):
    sha = uuid.uuid4().hex + uuid.uuid4().hex
    repo.register_source(sha, f"cas:///sources/{run_id}.xlsx", 1000, actor="curator-1")
    draft.source_uri = f"cas:///sources/{run_id}.xlsx"
    draft.file_sha256 = sha
    draft.base_versions = {k: ((repo.get_document(k) or {}).get("version") or 0) for k in draft.documents}
    return repo.stage(draft, expected_revision=0, actor="curator-1")


def _plan_and_stage(repo: DocumentRepository, label: str, values: list[object], run_id: str):
    planner = DocumentPlanner(extensions=repo.get_catalog_extensions())
    draft = planner.plan_records(_records(label, values), run_id=run_id)
    # a fresh variety per run keeps documents independent of earlier runs in the same database
    _stage(repo, draft, run_id)
    return draft


def _commit(repo: DocumentRepository, run_id: str):
    run = repo.get_run(run_id)
    return repo.commit(run_id, run["revision"], run["payload_sha256"], actor="curator-1")


@pytest.mark.integration
def test_register_new_persists_and_next_run_recognizes_label(db: Engine):
    repo = DocumentRepository(db)
    label = _novel()
    run_id = f"run_na_{uuid.uuid4().hex[:8]}"
    draft = _plan_and_stage(repo, label, ["1500", "1500"], run_id)
    items = [r for r in draft.reviews if r.category == "NEW_ATTRIBUTE"]
    assert len(items) == 2

    with pytest.raises(Conflict):
        _commit(repo, run_id)  # pending reviews block the commit

    resolved = repo.resolve_review(run_id, items[0].item_id,
                                   {"action": "REGISTER_NEW", "reason": "Atribut mutu buah baru", "label": label,
                                    "organ": "buah", "value_type": "number", "unit": "ppm"},
                                   actor="curator-1", actor_role="curator")
    assert resolved["status"] == "approved"
    run = repo.get_run(run_id)
    statuses = {r["item_id"]: r["status"] for r in run["draft"]["reviews"]}
    assert set(statuses[i.item_id] for i in items) == {"approved"}  # sibling resolved with the same decision

    # catalog row is written only at commit
    key = slugify_attribute_key(label)
    with db.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM kms.attribute_catalog_ext WHERE canonical_key=:k"), {"k": key}).scalar() == 0
    _commit(repo, run_id)
    with db.connect() as conn:
        row = conn.execute(text("SELECT organ, value_type, unit FROM kms.attribute_catalog_ext WHERE canonical_key=:k"),
                           {"k": key}).one()
    assert tuple(row) == ("buah", "number", "ppm")

    doc_key = next(iter(draft.documents))
    stored = repo.get_document(doc_key)
    assert stored["attributes"][f"attr_{key}"]["resolution"] == "HUMAN_REVIEW"

    # a later run knows the label: no review, value accepted automatically
    next_run = f"run_na_{uuid.uuid4().hex[:8]}"
    draft2 = _plan_and_stage(repo, label, ["1900"], next_run)
    assert not [r for r in draft2.reviews if r.category == "NEW_ATTRIBUTE"]
    assert f"attr_{key}" in next(iter(draft2.documents.values())).attributes


@pytest.mark.integration
def test_decision_guards(db: Engine):
    repo = DocumentRepository(db)
    label = _novel()
    run_id = f"run_na_{uuid.uuid4().hex[:8]}"
    draft = _plan_and_stage(repo, label, ["12"], run_id)
    item = next(r for r in draft.reviews if r.category == "NEW_ATTRIBUTE")
    base = {"action": "REGISTER_NEW", "reason": "Atribut baru yang valid", "label": label, "organ": "buah", "value_type": "number"}

    with pytest.raises(Conflict):
        repo.resolve_review(run_id, item.item_id, base, actor="rev-1", actor_role="reviewer")
    with pytest.raises(InvalidState):
        repo.resolve_review(run_id, item.item_id, {**base, "reason": "pendek"}, actor="c", actor_role="curator")
    with pytest.raises(InvalidState):  # collides with a template label
        repo.resolve_review(run_id, item.item_id, {**base, "label": "tinggi tanaman"}, actor="c", actor_role="curator")
    with pytest.raises(InvalidState):
        repo.resolve_review(run_id, item.item_id, {**base, "value_type": "nonsense"}, actor="c", actor_role="curator")
    assert repo.get_run(run_id)["draft"]["reviews"][0]["status"] == "pending"


@pytest.mark.integration
def test_map_to_existing_persists_alias_and_reject_is_remembered(db: Engine):
    repo = DocumentRepository(db)
    alias_label, refused = _novel(), _novel()

    run_a = f"run_na_{uuid.uuid4().hex[:8]}"
    draft_a = _plan_and_stage(repo, alias_label, ["95"], run_a)
    item_a = next(r for r in draft_a.reviews if r.category == "NEW_ATTRIBUTE")
    repo.resolve_review(run_a, item_a.item_id,
                        {"action": "MAP_TO_EXISTING", "reason": "Sinonim tinggi tanaman", "attribute_id": "attr_tinggi_tanaman"},
                        actor="c", actor_role="curator")
    _commit(repo, run_a)
    with db.connect() as conn:
        assert conn.execute(text("SELECT attribute_id FROM kms.attribute_alias_ext WHERE alias_norm=:n"),
                            {"n": alias_label.lower()}).scalar() == "attr_tinggi_tanaman"
    assert "attr_tinggi_tanaman" in repo.get_document(next(iter(draft_a.documents)))["attributes"]

    run_b = f"run_na_{uuid.uuid4().hex[:8]}"
    draft_b = _plan_and_stage(repo, refused, ["???"], run_b)
    item_b = next(r for r in draft_b.reviews if r.category == "NEW_ATTRIBUTE")
    repo.resolve_review(run_b, item_b.item_id, {"action": "REJECT", "reason": "Bukan karakter tanaman"},
                        actor="c", actor_role="curator")
    _commit(repo, run_b)
    run_c = f"run_na_{uuid.uuid4().hex[:8]}"
    draft_c = _plan_and_stage(repo, refused, ["???"], run_c)
    assert not [r for r in draft_c.reviews if r.category == "NEW_ATTRIBUTE"]


@pytest.mark.integration
def test_catalog_tables_are_append_only(db: Engine):
    with db.begin() as conn:
        conn.execute(text(
            "INSERT INTO kms.attribute_rejections (label_norm, source_label, created_from_run, created_by, reason) "
            "VALUES (:n, 'x', 'run_x', 'tester', 'uji tabel append-only') ON CONFLICT DO NOTHING"),
            {"n": f"append-only-{uuid.uuid4().hex[:6]}"})
    with pytest.raises(Exception):
        with db.begin() as conn:
            conn.execute(text("DELETE FROM kms.attribute_rejections"))


@pytest.mark.integration
def test_conflicting_rows_of_one_document_write_nothing(db: Engine):
    repo = DocumentRepository(db)
    label = _novel()
    run_id = f"run_na_{uuid.uuid4().hex[:8]}"
    draft = _plan_and_stage(repo, label, ["1500", "1700"], run_id)
    items = [r for r in draft.reviews if r.category == "NEW_ATTRIBUTE"]
    repo.resolve_review(run_id, items[0].item_id,
                        {"action": "REGISTER_NEW", "reason": "Atribut mutu buah baru", "label": label,
                         "organ": "buah", "value_type": "number", "unit": "ppm"},
                        actor="curator-1", actor_role="curator")
    run = repo.get_run(run_id)
    assert {r["status"] for r in run["draft"]["reviews"] if r["category"] == "NEW_ATTRIBUTE"} == {"rejected"}
    doc = next(iter(run["draft"]["documents"].values()))
    assert f"attr_{slugify_attribute_key(label)}" not in doc["attributes"]


def test_new_attribute_review_renders_curator_controls_not_generic_buttons():
    """NEW_ATTRIBUTE shows register / alias / reject controls (one form per label), never the 2-button layout."""
    from unittest.mock import MagicMock, patch

    from src.integrations import streamlit_commit
    from src.storage.document_contracts import DocumentDraft, DocumentReviewItem

    def item(item_id: str, value: str) -> DocumentReviewItem:
        return DocumentReviewItem(item_id=item_id, category="NEW_ATTRIBUTE", source_label="aroma buah",
                                  source_context="row", raw_values=[value], status="pending",
                                  target_document_key="plant_x:hab_y", payload={"raw_value": value, "similar_attributes": []})

    draft = DocumentDraft.model_construct(run_id="run_ui", reviews=[item("rev_a", "harum"), item("rev_b", "wangi")])
    keys: list[str] = []

    def button(label, key=None, **kwargs):
        keys.append(str(key))
        return False

    with patch("streamlit.expander") as expander, patch("streamlit.write"), patch("streamlit.subheader"), \
            patch("streamlit.warning"), patch("streamlit.text_input", return_value=""), \
            patch("streamlit.selectbox", return_value="x [attr_x]"), patch("streamlit.button", side_effect=button), \
            patch("streamlit.columns", side_effect=lambda spec: [MagicMock(button=button) for _ in range(spec if isinstance(spec, int) else len(spec))]), \
            patch.object(streamlit_commit, "fetch_catalog_extensions", return_value=CatalogExtensions()):
        expander.return_value.__enter__.return_value = MagicMock()
        expander.return_value.__exit__.return_value = False
        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui")

    assert sum(k.startswith("na_reg_") for k in keys) == 1  # two cells, one label: one form
    assert any(k.startswith("na_alias_") for k in keys) and any(k.startswith("na_rej_") for k in keys)
    assert not any(k.startswith("btn_app_") or k.startswith("btn_rej_") for k in keys)
