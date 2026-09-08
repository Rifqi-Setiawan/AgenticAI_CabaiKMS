from __future__ import annotations

import sqlite3

import openpyxl
import pytest

from src.agents.schema_matching.anchor import AnchorResult
from src.agents.schema_matching.retrieval import RetrievalHit
from src.orchestrator.graph import NODE_ORDER, _sqlite_checkpointer, build_graph
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import SchemaMapping
from src.ui import pipeline_runner as runner


def _source(tmp_path, attribute="Unknown attribute"):
    path = tmp_path / "runtime.xlsx"
    wb = openpyxl.Workbook(); ws = wb.active
    ws.append(["Variety", attribute]); ws.append(["Domba", "perdu"])
    wb.save(path); wb.close(); return path


def _wire_schema(monkeypatch, calls):
    schema = CanonicalSchema.from_template(); target = schema.row_by_label("habitus")
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **k: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "ensure_indexed", lambda *a, **k: object())
    monkeypatch.setattr(runner, "retrieve", lambda *a, **k: [RetrievalHit(target.id, target.label, target.domain, 0.1, canonical_key=target.canonical_key)])
    def mapping(profile, candidates, state, *, source_format, **kwargs):
        calls.append(profile.attribute_name)
        return SchemaMapping(source_attribute=profile.attribute_name, source_format=source_format,
            target_canonical_row=target.id, confidence=0.99, reasoning="mock", normalization_required=True), {}
    monkeypatch.setattr(runner, "safe_rerank", mapping)


def test_graph_has_real_coarse_runtime_topology():
    assert NODE_ORDER == ("source_ingestion", "schema_matching_tabular", "drive_crawler", "vision_classification", "finalization")
    graph = build_graph().get_graph()
    text = " ".join(graph.nodes)
    assert "stub" not in text
    assert "schema_matching_tabular" in text


def test_tabular_checkpoint_resume_does_not_repeat_schema_matching(tmp_path, monkeypatch):
    source, db, calls = _source(tmp_path), tmp_path / "runtime.sqlite", []
    _wire_schema(monkeypatch, calls)
    partial = runner._run_pipeline_ui_impl(source, _run_id="resume-run", checkpoint_db_path=db,
        _interrupt_after=["schema_matching_tabular"])
    assert partial["workbook_bytes"]
    assert calls == ["Unknown attribute"]

    result = runner.resume_pipeline_ui(source, run_id="resume-run", checkpoint_db_path=db)
    assert calls == ["Unknown attribute"]
    assert result.run_id == "resume-run"
    assert result.canonical_df.loc[result.canonical_df.Karakter == "habitus", "Domba"].item() == "perdu"


def test_resume_matches_uninterrupted_output(tmp_path, monkeypatch):
    source, calls = _source(tmp_path), []
    _wire_schema(monkeypatch, calls)
    uninterrupted = runner._run_pipeline_ui_impl(source, _run_id="full", checkpoint_db_path=tmp_path / "full.sqlite")
    runner._run_pipeline_ui_impl(source, _run_id="resumed", checkpoint_db_path=tmp_path / "resume.sqlite",
                                 _interrupt_after=["schema_matching_tabular"])
    resumed = runner.resume_pipeline_ui(source, run_id="resumed", checkpoint_db_path=tmp_path / "resume.sqlite")
    assert uninterrupted.workbook_bytes == resumed.workbook_bytes
    assert uninterrupted.mapping_df.drop(columns="review_item_id").equals(resumed.mapping_df.drop(columns="review_item_id"))


def test_resume_rejects_mismatched_source_or_configuration(tmp_path, monkeypatch):
    source, calls, db = _source(tmp_path), [], tmp_path / "mismatch.sqlite"
    _wire_schema(monkeypatch, calls)
    runner._run_pipeline_ui_impl(source, _run_id="mismatch", checkpoint_db_path=db,
                                 _interrupt_after=["schema_matching_tabular"])
    with pytest.raises(ValueError, match="identity"):
        runner.resume_pipeline_ui(source, run_id="mismatch", k=9, checkpoint_db_path=db)


def test_run_ids_have_isolated_real_checkpoints(tmp_path, monkeypatch):
    source, calls, db = _source(tmp_path), [], tmp_path / "isolated.sqlite"
    _wire_schema(monkeypatch, calls)
    runner._run_pipeline_ui_impl(source, _run_id="run-a", checkpoint_db_path=db)
    runner._run_pipeline_ui_impl(source, _run_id="run-b", checkpoint_db_path=db)
    with _sqlite_checkpointer(db) as cp:
        assert cp.get({"configurable": {"thread_id": "run-a"}})["channel_values"]["run_id"] == "run-a"
        assert cp.get({"configurable": {"thread_id": "run-b"}})["channel_values"]["run_id"] == "run-b"
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT count(*) FROM checkpoints").fetchone()[0] > 0


def test_no_drive_routes_directly_to_finalization(tmp_path, monkeypatch):
    source, calls = _source(tmp_path, "Seeds per mature fruit"), []
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **k: AnchorResult("found", "Variety", 1.0, "test"))
    monkeypatch.setattr(runner, "list_images", lambda *a, **k: pytest.fail("Drive must be skipped"))
    monkeypatch.setattr(runner, "VisionSession", lambda: pytest.fail("vision must be skipped"))
    result = runner._run_pipeline_ui_impl(source, checkpoint_db_path=tmp_path / "skip.sqlite")
    assert result.agent_status["vision_classification"].startswith("dilewati")


def test_graph_matches_shared_direct_tabular_stage(tmp_path, monkeypatch):
    source, calls = _source(tmp_path, "Seeds per mature fruit"), []
    monkeypatch.setattr(runner, "detect_anchor", lambda *a, **k: AnchorResult("found", "Variety", 1.0, "test"))
    direct = runner._run_pipeline_ui_stage_impl(source, _run_id="parity", _skip_checkpoint=True)
    graph = runner._run_pipeline_ui_impl(source, _run_id="parity", checkpoint_db_path=tmp_path / "parity.sqlite")
    assert direct.workbook_bytes == graph.workbook_bytes
    assert direct.mapping_df.equals(graph.mapping_df)
    assert direct.canonical_df.equals(graph.canonical_df)
    assert direct.provenance_records == graph.provenance_records
    assert direct.error_trace == graph.error_trace
