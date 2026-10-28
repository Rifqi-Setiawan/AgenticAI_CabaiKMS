from __future__ import annotations

import sqlite3
import inspect
from types import SimpleNamespace

import openpyxl
import pytest

from src.agents.schema_matching.anchor import AnchorResult
from src.agents.schema_matching.retrieval import RetrievalHit
from src.orchestrator.graph import NODE_ORDER, _sqlite_checkpointer, build_graph
from src.schema.canonical import CanonicalSchema
from src.schema.contracts import ImageMetadata, SchemaMapping, VisionResult
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


def _wire_one_image(monkeypatch, calls):
    image = ImageMetadata(
        file_id="image-1",
        filename="leaf.jpg",
        mime_type="image/jpeg",
        size=10,
        created_time="2026-01-01T00:00:00Z",
    )
    monkeypatch.setattr(runner, "normalize_folder_id", lambda folder: folder)

    def list_once(folder):
        calls["drive"] += 1
        return [image]

    def classify_once(*args, **kwargs):
        calls["vision"] += 1
        return VisionResult(
            classification_status="KNOWN",
            matched_variety="Domba",
            identified_part="DAUN",
            confidence=0.9,
            visual_evidence="mock",
        ), {}

    monkeypatch.setattr(runner, "list_images", list_once)
    monkeypatch.setattr(
        runner,
        "VisionSession",
        lambda: SimpleNamespace(knowledge_source_text="knowledge", varieties=[]),
    )
    monkeypatch.setattr(runner, "safe_classify_image", classify_once)


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
    direct = runner._run_tabular_stage_impl(source, _run_id="parity")
    graph = runner._run_pipeline_ui_impl(source, _run_id="parity", checkpoint_db_path=tmp_path / "parity.sqlite")
    assert direct.workbook_bytes == graph.workbook_bytes
    assert direct.mapping_df.equals(graph.mapping_df)
    assert direct.canonical_df.equals(graph.canonical_df)
    assert direct.provenance_records == graph.provenance_records
    assert direct.error_trace == graph.error_trace


def test_tabular_stage_api_has_no_multimodal_execution_path():
    parameters = inspect.signature(runner._run_tabular_stage_impl).parameters
    assert "drive_folder_id" not in parameters
    assert "max_images" not in parameters
    assert "vision_rate_limiter" not in parameters


def test_full_graph_owns_exactly_one_drive_and_vision_call(tmp_path, monkeypatch):
    source, schema_calls = _source(tmp_path), []
    multimodal_calls = {"drive": 0, "vision": 0}
    _wire_schema(monkeypatch, schema_calls)
    _wire_one_image(monkeypatch, multimodal_calls)

    result = runner._run_pipeline_ui_impl(
        source,
        drive_folder_id="folder",
        checkpoint_db_path=tmp_path / "one-image.sqlite",
    )

    assert schema_calls == ["Unknown attribute"]
    assert multimodal_calls == {"drive": 1, "vision": 1}
    assert len(result.vision_rows) == 1


def test_drive_checkpoint_resume_does_not_repeat_listing(tmp_path, monkeypatch):
    source, schema_calls = _source(tmp_path), []
    db = tmp_path / "drive-resume.sqlite"
    multimodal_calls = {"drive": 0, "vision": 0}
    _wire_schema(monkeypatch, schema_calls)
    _wire_one_image(monkeypatch, multimodal_calls)

    partial = runner._run_pipeline_ui_impl(
        source,
        drive_folder_id="folder",
        _run_id="drive-resume",
        checkpoint_db_path=db,
        _interrupt_after=["drive_crawler"],
    )
    assert partial["image_metadata"]
    assert schema_calls == ["Unknown attribute"]
    assert multimodal_calls == {"drive": 1, "vision": 0}

    result = runner.resume_pipeline_ui(
        source,
        run_id="drive-resume",
        drive_folder_id="folder",
        checkpoint_db_path=db,
    )

    assert schema_calls == ["Unknown attribute"]
    assert multimodal_calls == {"drive": 1, "vision": 1}
    assert result.run_id == "drive-resume"
    assert len(result.vision_rows) == 1
