from __future__ import annotations

import io

import openpyxl
import pandas as pd
import pytest

from src.agents.schema_matching import review_queue
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import NULL_ROW, SchemaMapping
from src.ui import pipeline_runner
from src.ui.output_builder import CanonicalOutputBuilder
from src.ui.pipeline_runner import PipelineRunResult, _deterministic_workbook_bytes
from src.ui.review_replay import apply_review_corrections


def _mapping(schema: CanonicalSchema, target_label: str = "habitus") -> SchemaMapping:
    return SchemaMapping(
        source_attribute="Growth habit", source_context="Vegetative",
        source_format="row-oriented",
        target_canonical_row=schema.row_by_label(target_label).id,
        confidence=0.2, reasoning="uncertain model proposal",
        normalization_required=True,
    )


def _fixture(
    tmp_path, *, existing_value: str | None = None, null_proposal: bool = False,
):
    schema = CanonicalSchema.from_template()
    queue = tmp_path / "review.jsonl"
    run_id = "run-current"
    source_hash = "a" * 64
    proposed = None if null_proposal else schema.row_by_label("habitus")
    mapping = (
        SchemaMapping(
            source_attribute="Growth habit", source_context="Vegetative",
            source_format="row-oriented", target_canonical_row=NULL_ROW,
            confidence=0.2, reasoning="no model proposal",
            normalization_required=True,
        )
        if null_proposal else _mapping(schema)
    )
    item = review_queue.enqueue(
        mapping, reason="manual review required", queue_path=queue,
        run_id=run_id, mapping_item_id="mapping-1", source_file_name="source.xlsx",
        source_file_sha256=source_hash, source_sheet="Observations",
        source_format="row-oriented", source_attribute_display="Vegetative / Growth habit",
        mapping_identity_kind="source_attribute_display",
        mapping_identity_value="Vegetative / Growth habit",
        schema_version=schema.schema_version, template_hash=schema.template_hash,
        proposed_canonical_key=proposed.canonical_key if proposed else None,
        mapping_method="retrieve_rerank", verifier_status="REVIEW",
        verifier_warnings=["LOW_CONFIDENCE"], raw_values_by_variety={"Domba": ["terna"]},
    )
    builder = CanonicalOutputBuilder(schema=schema, variety_names=["Domba"])
    if existing_value is not None and proposed is not None:
        builder.set_cell(proposed.id, "Domba", existing_value)
    workbook = builder.build_workbook()
    original_bytes = _deterministic_workbook_bytes(workbook)
    workbook.close()
    mapping_df = pd.DataFrame([{
        "review_item_id": item.item_id, "mapping_item_id": "mapping-1",
        "source_file_sha256": source_hash, "source_sheet": "Observations",
        "source_format": "row-oriented", "canonical_write": False,
        "predicted_row": proposed.id if proposed else NULL_ROW,
        "proposed_target_canonical_key": proposed.canonical_key if proposed else None,
    }])
    result = PipelineRunResult(
        mapping_df=mapping_df, canonical_df=pd.DataFrame(), workbook_bytes=original_bytes,
        vision_rows=[], run_id=run_id, checkpoint_thread_id=run_id,
        review_queue_path=str(queue), schema_version=schema.schema_version,
        template_hash=schema.template_hash,
    )
    return schema, queue, item, result


def _cell(result: PipelineRunResult, schema: CanonicalSchema, label: str):
    workbook = openpyxl.load_workbook(io.BytesIO(result.workbook_bytes), data_only=True)
    try:
        row_number = schema.rows.index(schema.row_by_label(label)) + 2
        return workbook["Sheet1"].cell(row=row_number, column=3).value
    finally:
        workbook.close()


def test_approve_current_mapping_and_replay(tmp_path):
    schema, queue, item, original = _fixture(tmp_path)
    resolved = review_queue.approve(
        item.item_id, resolved_by="reviewer", expected_run_id=original.run_id,
        queue_path=queue,
    )
    assert resolved.status == "approved"
    assert resolved.final_canonical_key == schema.row_by_label("habitus").canonical_key
    corrected = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert _cell(corrected, schema, "habitus") == "terna"


def test_revise_to_valid_key_changes_expected_output_and_provenance(tmp_path):
    schema, queue, item, original = _fixture(tmp_path)
    target = schema.row_by_label("tinggi tanaman")
    review_queue.revise_to_canonical_key(
        item.item_id, target.canonical_key, schema=schema, resolved_by="reviewer",
        expected_run_id=original.run_id, queue_path=queue,
    )
    corrected = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert _cell(corrected, schema, "habitus") is None
    assert _cell(corrected, schema, "tinggi tanaman") == "terna"
    record = corrected.provenance_records[-1]
    assert record.mapping_method == "human_review"
    assert record.review_resolution == "revised"
    assert record.original_proposed_canonical_key == schema.row_by_label("habitus").canonical_key
    assert record.canonical_key == target.canonical_key
    assert record.resolved_by == "reviewer"


def test_invalid_canonical_key_is_rejected_without_appending_event(tmp_path):
    schema, queue, item, original = _fixture(tmp_path)
    before = queue.read_text(encoding="utf-8").splitlines()
    with pytest.raises(ValueError, match="unknown canonical_key"):
        review_queue.revise_to_canonical_key(
            item.item_id, "not_a_real_key", schema=schema,
            expected_run_id=original.run_id, queue_path=queue,
        )
    assert queue.read_text(encoding="utf-8").splitlines() == before


def test_no_match_writes_nothing(tmp_path):
    schema, queue, item, original = _fixture(tmp_path)
    resolved = review_queue.mark_no_match(
        item.item_id, resolved_by="reviewer", expected_run_id=original.run_id,
        queue_path=queue,
    )
    assert resolved.status == "no_match"
    corrected = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert _cell(corrected, schema, "habitus") is None
    assert corrected.provenance_records == []


def test_replay_never_calls_model_retrieval_verifier_or_vision(tmp_path, monkeypatch):
    schema, queue, item, original = _fixture(tmp_path)
    review_queue.approve(item.item_id, expected_run_id=original.run_id, queue_path=queue)
    for name in ("retrieve", "safe_rerank", "verify_mapping", "safe_classify_image"):
        monkeypatch.setattr(pipeline_runner, name, lambda *a, **k: pytest.fail(f"{name} called"))
    apply_review_corrections(original, queue_path=queue, schema=schema)


def test_replay_is_idempotent_and_does_not_duplicate_values(tmp_path):
    schema, queue, item, original = _fixture(tmp_path, existing_value="terna")
    review_queue.approve(item.item_id, expected_run_id=original.run_id, queue_path=queue)
    first = apply_review_corrections(original, queue_path=queue, schema=schema)
    second = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert first.workbook_bytes == second.workbook_bytes
    assert _cell(first, schema, "habitus") == "terna"
    assert "; " not in _cell(first, schema, "habitus")


def test_historical_run_cannot_be_resolved_as_current_run(tmp_path):
    schema, queue, item, original = _fixture(tmp_path)
    with pytest.raises(ValueError, match="belongs to run"):
        review_queue.approve(
            item.item_id, expected_run_id="different-run", queue_path=queue,
        )
    assert len(review_queue.list_pending(queue_path=queue, run_id=original.run_id)) == 1


def test_queue_history_is_append_only_for_no_match(tmp_path):
    _, queue, item, original = _fixture(tmp_path)
    before = queue.read_text(encoding="utf-8").splitlines()
    review_queue.mark_no_match(
        item.item_id, expected_run_id=original.run_id, queue_path=queue,
    )
    after = queue.read_text(encoding="utf-8").splitlines()
    assert after[:1] == before
    assert len(after) == len(before) + 1


def test_null_proposal_no_match_replays_without_writing(tmp_path):
    schema, queue, item, original = _fixture(tmp_path, null_proposal=True)
    resolved = review_queue.mark_no_match(
        item.item_id, expected_run_id=original.run_id, queue_path=queue,
    )
    assert resolved.final_canonical_key is None
    corrected = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert _cell(corrected, schema, "habitus") is None
    assert corrected.provenance_records == []


def test_null_proposal_can_be_revised_and_replayed_to_valid_key(tmp_path):
    schema, queue, item, original = _fixture(tmp_path, null_proposal=True)
    target = schema.row_by_label("habitus")
    resolved = review_queue.revise_to_canonical_key(
        item.item_id, target.canonical_key, schema=schema,
        expected_run_id=original.run_id, queue_path=queue,
    )
    assert resolved.final_canonical_key == target.canonical_key
    corrected = apply_review_corrections(original, queue_path=queue, schema=schema)
    assert _cell(corrected, schema, "habitus") == "terna"
