"""Dynamic schema stage 2: acquisition of unmapped attributes as new canonical rows, without duplicates."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy.engine import Engine

from src.agents.schema_matching import acquisition
from src.agents.schema_matching.acquisition import AcquisitionItem, AcquisitionPlan, Candidate
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "samples" / "data_input.xlsx"


@pytest.fixture(autouse=True)
def _reset_known_rows():
    from src.schema import dynamic

    yield
    dynamic._KNOWN_EXTRA_IDS.clear()


def _cand(i: int, name: str, samples=("12", "14")) -> Candidate:
    return Candidate(index=i, display_name=name, context="", samples=list(samples), nearest=["r_1: habitus"])


def _item(i, label, group, domain="buah", ok=True, same=acquisition.NULL_REF):
    return AcquisitionItem(index=i, is_characteristic=ok, canonical_label=label, domain=domain, group=group, same_as_existing=same)


class _FakeStore:
    """In-memory stand-in for the acquisition endpoint: idempotent by normalized label."""

    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}
        self.calls: list[dict] = []

    def __call__(self, payload: dict) -> dict:
        self.calls.append(payload)
        key = payload["label"].strip().lower()
        if key in self.rows:
            return {"created": False, "duplicate_of": self.rows[key]["canonical_key"], "row": None}
        slug = "_".join(key.replace("(", " ").replace(")", " ").split())
        row = {"seq": len(self.rows) + 1, "canonical_key": slug, "label": payload["label"], "domain": payload["domain"],
               "examples": payload["examples"], "aliases": [a.lower() for a in payload.get("aliases", [])], "status": "provisional"}
        self.rows[key] = row
        return {"created": True, "duplicate_of": None, "row": row}


def test_guard_skips_identity_columns_and_empty_columns():
    assert not acquisition.passes_guard("No", ["1"])
    assert not acquisition.passes_guard("Data Koordinat / S", ["110.4"])
    assert not acquisition.passes_guard("Catatan Surveyor", ["x"])
    assert not acquisition.passes_guard("Kadar Capsaicin", ["", "  "])
    assert acquisition.passes_guard("Kadar Capsaicin (ppm)", ["1500"])


def test_synonyms_in_one_run_become_one_row_and_existing_meaning_is_not_duplicated(monkeypatch):
    cands = [_cand(0, "Kadar Capsaicin (ppm)"), _cand(1, "Capsaicin content"), _cand(2, "Aroma Buah"),
             _cand(3, "Tinggi tanaman saat dewasa"), _cand(4, "Catatan umum")]
    plan = AcquisitionPlan(items=[
        _item(0, "Kadar capsaicin", group=1), _item(1, "Kadar capsaicin", group=1), _item(2, "Aroma buah", group=2),
        _item(3, "Tinggi tanaman", group=3, domain="vegetatif", same="r_5"), _item(4, "Catatan", group=4, ok=False),
    ])
    monkeypatch.setattr(acquisition, "plan", lambda c, llm_call=None, catalog=(): plan)
    store = _FakeStore()
    out = acquisition.acquire(cands, existing_row_ids={"r_5"}, acquire_call=store, run_id="run_t", source_sha256="a" * 64)
    assert [o.status for o in out] == ["NEW_ROW", "NEW_ROW", "NEW_ROW", "DUPLICATE_OF", "NOT_CHARACTERISTIC"]
    assert out[0].row.canonical_key == out[1].row.canonical_key  # synonyms share one row
    assert len(store.rows) == 2  # only two rows created for five candidates
    assert store.calls[0]["aliases"] == ["Capsaicin content", "Kadar Capsaicin (ppm)"] or store.calls[0]["aliases"] == ["Capsaicin content"]
    assert out[3].duplicate_of == "r_5"


def test_known_label_from_an_earlier_run_is_reported_as_duplicate_not_recreated(monkeypatch):
    store = _FakeStore()
    monkeypatch.setattr(acquisition, "plan", lambda c, llm_call=None, catalog=(): AcquisitionPlan(items=[_item(0, "Aroma buah", 1)]))
    first = acquisition.acquire([_cand(0, "Aroma")], existing_row_ids=set(), acquire_call=store, run_id="r1", source_sha256="a" * 64)
    second = acquisition.acquire([_cand(0, "Aroma")], existing_row_ids=set(), acquire_call=store, run_id="r2", source_sha256="a" * 64)
    assert first[0].status == "NEW_ROW" and second[0].status == "DUPLICATE_OF"
    assert len(store.rows) == 1


def test_judge_failure_never_aborts_and_creates_nothing(monkeypatch):
    def boom(c, llm_call=None, catalog=()):
        raise RuntimeError("model down")

    monkeypatch.setattr(acquisition, "plan", boom)
    store = _FakeStore()
    out = acquisition.acquire([_cand(0, "Aroma")], existing_row_ids=set(), acquire_call=store, run_id="r", source_sha256="a" * 64)
    assert out[0].status == "FAILED" and not store.rows


def test_pipeline_stage_adds_rows_to_excel_without_touching_template_rows(monkeypatch, tmp_path):
    """Flag on, matcher returns NULL for everything, judge accepts: Excel gains rows below the 60 template rows."""
    from src.ui import pipeline_runner as pr

    monkeypatch.setenv("KMS_DYNAMIC_SCHEMA", "true")
    store = _FakeStore()
    monkeypatch.setattr(pr, "_make_acquire_call", lambda: store)

    def null_rerank(profile, retrieved, state, **kwargs):
        mapping = SchemaMapping(source_attribute=profile.attribute_name, source_context=profile.structural_context,
                                source_format="row-oriented", target_canonical_row=NULL_ROW, confidence=0.1,
                                reasoning="uji", normalization_required=False)
        return mapping, {}

    monkeypatch.setattr(pr, "safe_rerank", null_rerank)

    def judge(cands, llm_call=None, catalog=()):
        return AcquisitionPlan(items=[_item(c.index, f"Atribut Uji {c.index}", group=c.index, domain="vegetatif") for c in cands])

    monkeypatch.setattr(acquisition, "plan", judge)
    result = pr._run_tabular_stage_impl(
        SAMPLE, source_format="row-oriented", sheet_name="Resume Data", retrieval_backend="exact",
        review_queue_path=tmp_path / "queue.jsonl",
    )
    base = CanonicalSchema.from_template()
    new = [r for r in result.extension_rows]
    assert new and len(new) == len(store.rows)
    assert result.schema_version.startswith(base.schema_version + "+ext.")
    assert (result.mapping_df["acquisition_status"] == "NEW_ROW").sum() >= 1
    assert result.canonical_df.shape[0] == len(base.rows) + len(new)
    assert list(result.canonical_df["Karakter"][: len(base.rows)]) == [r.label for r in base.rows]
    import io

    import openpyxl

    ws = openpyxl.load_workbook(io.BytesIO(result.workbook_bytes)).active
    assert ws.max_row == len(base.rows) + len(new) + 1
    assert ws.cell(row=len(base.rows) + 2, column=2).value == new[0].label
    assert any(ws.cell(row=len(base.rows) + 2, column=c).value for c in range(3, ws.max_column + 1))
    assert result.evaluation_config_fingerprint


def _null_rerank(profile, retrieved, state, **kwargs):
    mapping = SchemaMapping(source_attribute=profile.attribute_name, source_context=profile.structural_context,
                            source_format="row-oriented", target_canonical_row=NULL_ROW, confidence=0.1,
                            reasoning="uji", normalization_required=False)
    return mapping, {}


def test_acquired_attributes_are_not_left_pending_in_the_review_queue(monkeypatch, tmp_path):
    """An attribute that got a row (AUTO_ACCEPT) must not also sit in the review queue as pending."""
    import pandas as pd

    from src.agents.schema_matching import review_queue
    from src.ui import pipeline_runner as pr

    monkeypatch.setenv("KMS_DYNAMIC_SCHEMA", "true")
    monkeypatch.setattr(pr, "_make_acquire_call", lambda: _FakeStore())
    monkeypatch.setattr(pr, "safe_rerank", _null_rerank)
    monkeypatch.setattr(acquisition, "plan", lambda cands, llm_call=None, catalog=(): AcquisitionPlan(
        items=[_item(c.index, f"Atribut Uji {c.index}", group=c.index, domain="vegetatif") for c in cands]))
    queue = tmp_path / "queue.jsonl"
    result = pr._run_tabular_stage_impl(SAMPLE, source_format="row-oriented", sheet_name="Resume Data",
                                        retrieval_backend="exact", review_queue_path=queue)
    df = result.mapping_df
    acquired = df[df["acquisition_status"] == "NEW_ROW"]
    assert len(acquired) >= 1
    pending_ids = {item.item_id for item in review_queue.list_pending(queue, run_id=result.run_id)}
    for _, row in acquired.iterrows():
        assert pd.isna(row["review_item_id"]) or not row["review_item_id"]
        assert row["acceptance_status"] == "AUTO_ACCEPT"
    assert pending_ids == {r for r in df["review_item_id"].dropna() if r}


def test_candidates_that_are_not_acquired_still_reach_the_review_queue(monkeypatch, tmp_path):
    from src.agents.schema_matching import review_queue
    from src.ui import pipeline_runner as pr

    monkeypatch.setenv("KMS_DYNAMIC_SCHEMA", "true")
    monkeypatch.setattr(pr, "_make_acquire_call", lambda: _FakeStore())
    monkeypatch.setattr(pr, "safe_rerank", _null_rerank)
    monkeypatch.setattr(acquisition, "plan", lambda cands, llm_call=None, catalog=(): AcquisitionPlan(
        items=[_item(c.index, "x", group=c.index, ok=False) for c in cands]))
    queue = tmp_path / "queue.jsonl"
    result = pr._run_tabular_stage_impl(SAMPLE, source_format="row-oriented", sheet_name="Resume Data",
                                        retrieval_backend="exact", review_queue_path=queue)
    df = result.mapping_df
    rejected = df[df["acquisition_status"] == "NOT_CHARACTERISTIC"]
    assert len(rejected) >= 1
    assert all(isinstance(v, str) and v for v in rejected["review_item_id"])
    pending = {item.item_id for item in review_queue.list_pending(queue, run_id=result.run_id)}
    assert set(rejected["review_item_id"]) <= pending


def test_flag_off_pipeline_has_no_acquisition_column(monkeypatch, tmp_path):
    from src.ui import pipeline_runner as pr

    monkeypatch.delenv("KMS_DYNAMIC_SCHEMA", raising=False)

    def null_rerank(profile, retrieved, state, **kwargs):
        return SchemaMapping(source_attribute=profile.attribute_name, source_context=profile.structural_context,
                             source_format="row-oriented", target_canonical_row=NULL_ROW, confidence=0.1,
                             reasoning="uji", normalization_required=False), {}

    monkeypatch.setattr(pr, "safe_rerank", null_rerank)
    result = pr._run_tabular_stage_impl(SAMPLE, source_format="row-oriented", sheet_name="Resume Data",
                                        retrieval_backend="exact", review_queue_path=tmp_path / "queue.jsonl")
    assert "acquisition_status" not in result.mapping_df.columns
    assert result.extension_rows == ()
    assert result.schema_version == CanonicalSchema.from_template().schema_version
    assert result.canonical_df.shape[0] == len(CanonicalSchema.from_template().rows)


# ----------------------------------------------------------------------------- database
@pytest.fixture
def db() -> Engine:
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not configured; PostgreSQL test database required.")
    from src.storage.config import Settings
    from src.storage.db import make_engine
    from src.storage.migrate import migrate

    migrate(os.getenv("TEST_DATABASE_ADMIN_URL", url))
    engine = make_engine(Settings(_env_file=None, database_url=url))
    yield engine
    engine.dispose()


@pytest.mark.integration
def test_aliases_are_stored_and_make_a_later_label_a_duplicate(db: Engine):
    from src.storage.schema_rows import SchemaRowRepository

    repo = SchemaRowRepository(db)
    tag = uuid.uuid4().hex[:6]
    first = repo.acquire(label=f"Kadar Zat Pahit {tag}", domain="buah", examples=["3"], source_label="x", run_id="r",
                         source_sha256=None, actor="t", reason="uji alias", aliases=[f"Bitter content {tag}", f"Rasa pahit {tag}"])
    assert first["created"]
    assert len(first["row"]["aliases"]) == 2
    later = repo.acquire(label=f"BITTER CONTENT {tag}", domain="buah", examples=[], source_label="y", run_id="r2",
                         source_sha256=None, actor="t", reason="uji alias")
    assert not later["created"] and later["duplicate_of"] == first["row"]["canonical_key"]


def test_prompt_carries_the_full_row_listing_and_the_merge_rule():
    msgs = acquisition.build_messages([_cand(0, "Mahkota")], ["r_23: warna mahkota (bunga)", "r_5: panjang daun (daun)"])
    assert "DAFTAR SELURUH BARIS" in msgs[1]["content"] and "r_23: warna mahkota (bunga)" in msgs[1]["content"]
    assert "ATRIBUT TANPA PADANAN" in msgs[1]["content"]
    assert "HANYA untuk atribut yang benar-benar tidak ada padanannya" in msgs[0]["content"]


def test_duplicate_of_existing_row_writes_into_that_row_instead_of_dropping_the_value(monkeypatch, tmp_path):
    """The judge says 'same as r_N': the value lands in that row (status MERGED_TO), no new row is created."""
    from src.ui import pipeline_runner as pr

    monkeypatch.setenv("KMS_DYNAMIC_SCHEMA", "true")
    store = _FakeStore()
    monkeypatch.setattr(pr, "_make_acquire_call", lambda: store)
    base = CanonicalSchema.from_template()
    target = next(r for r in base.rows if r.label == "bentuk buah")

    def null_rerank(profile, retrieved, state, **kwargs):
        return SchemaMapping(source_attribute=profile.attribute_name, source_context=profile.structural_context,
                             source_format="row-oriented", target_canonical_row=NULL_ROW, confidence=0.1,
                             reasoning="uji", normalization_required=False), {}

    monkeypatch.setattr(pr, "safe_rerank", null_rerank)
    monkeypatch.setattr(acquisition, "plan", lambda cands, llm_call=None, catalog=(): AcquisitionPlan(
        items=[_item(c.index, "bentuk buah", group=c.index, same=target.id) for c in cands]))
    result = pr._run_tabular_stage_impl(SAMPLE, source_format="row-oriented", sheet_name="Resume Data",
                                        retrieval_backend="exact", review_queue_path=tmp_path / "queue.jsonl")
    assert not store.rows and result.extension_rows == ()
    merged = result.mapping_df[result.mapping_df["acquisition_status"] == f"MERGED_TO:{target.canonical_key}"]
    assert len(merged) >= 1 and set(merged["proposed_target_canonical_key"]) == {target.canonical_key}
    assert result.canonical_df.shape[0] == len(base.rows)


def test_candidates_are_judged_in_small_batches_with_retry_and_growing_listing(monkeypatch):
    seen_catalogs, calls = [], {"n": 0}

    def flaky_plan(cands, llm_call=None, catalog=()):
        calls["n"] += 1
        seen_catalogs.append(list(catalog))
        if calls["n"] == 1:
            raise RuntimeError("request timed out")  # first attempt of the first batch fails and is retried
        return AcquisitionPlan(items=[_item(c.index, f"Atribut {c.index}", group=c.index) for c in cands])

    monkeypatch.setattr(acquisition, "plan", flaky_plan)
    store = _FakeStore()
    cands = [_cand(i, f"Sumber {i}") for i in range(acquisition.BATCH_SIZE + 3)]
    out = acquisition.acquire(cands, existing_row_ids=set(), acquire_call=store, run_id="r", source_sha256="a" * 64,
                              catalog=["r_1: habitus (vegetatif)"], row_id_of=lambda row: f"r_{100 + row.seq}", retry_delay=0)
    assert all(o.status == "NEW_ROW" for o in out) and len(store.rows) == len(cands)
    assert calls["n"] == 3  # one retry + two batches
    assert any(line.startswith("r_101: ") for line in seen_catalogs[-1])  # second batch sees rows acquired by the first


def test_a_batch_that_keeps_failing_is_reported_but_other_batches_still_run(monkeypatch):
    def plan_fn(cands, llm_call=None, catalog=()):
        if cands[0].index == 0:
            raise RuntimeError("model unavailable")
        return AcquisitionPlan(items=[_item(c.index, f"Atribut {c.index}", group=c.index) for c in cands])

    monkeypatch.setattr(acquisition, "plan", plan_fn)
    store = _FakeStore()
    cands = [_cand(i, f"Sumber {i}") for i in range(acquisition.BATCH_SIZE + 2)]
    out = acquisition.acquire(cands, existing_row_ids=set(), acquire_call=store, run_id="r", source_sha256="a" * 64, retry_delay=0)
    assert [o.status for o in out[:acquisition.BATCH_SIZE]] == ["FAILED"] * acquisition.BATCH_SIZE
    assert "model unavailable" in out[0].note
    assert [o.status for o in out[acquisition.BATCH_SIZE:]] == ["NEW_ROW", "NEW_ROW"]
