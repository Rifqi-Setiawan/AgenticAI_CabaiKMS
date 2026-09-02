from __future__ import annotations

import sqlite3
import uuid

import pytest
from langgraph.errors import EmptyInputError

from src.orchestrator.graph import (
    LOW_CONFIDENCE_THRESHOLD,
    _sqlite_checkpointer,
    resume_pipeline,
    route_after_vision,
    run_pipeline,
)
from src.schema.contracts import VisionResult

SPREADSHEET = "data/samples/data_input.xlsx"
DRIVE_URL = "https://drive.google.com/drive/folders/stub"


def _thread_id() -> str:
    return uuid.uuid4().hex


def _vision_result(confidence: float) -> VisionResult:
    return VisionResult(
        classification_status="KNOWN",
        matched_variety="stub-varietas",
        identified_part="DAUN",
        confidence=confidence,
        visual_evidence="test fixture",
    )


class TestRouteAfterVision:
    """route_after_vision is pure — test it directly rather than only
    through a full graph run, so each branch is unambiguously exercised."""

    def test_continue_when_confident_and_no_errors(self):
        state = {"error_trace": [], "classification_results": [_vision_result(0.9)]}
        assert route_after_vision(state) == "continue"

    def test_retry_when_confidence_below_threshold(self):
        state = {
            "error_trace": [],
            "classification_results": [_vision_result(LOW_CONFIDENCE_THRESHOLD - 0.1)],
        }
        assert route_after_vision(state) == "retry"

    def test_retry_when_error_already_flagged_and_under_cap(self):
        state = {"error_trace": ["one prior issue"], "classification_results": [_vision_result(0.9)]}
        assert route_after_vision(state) == "retry"

    def test_manual_review_once_retries_exhausted(self):
        state = {
            "error_trace": ["issue 1", "issue 2"],
            "classification_results": [_vision_result(0.1)],
        }
        assert route_after_vision(state) == "manual_review"


class TestPipelineStateFlow:
    def test_happy_path_fills_expected_state_and_reaches_finalization(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        result = run_pipeline(
            SPREADSHEET, DRIVE_URL, db_path=db_path, thread_id=_thread_id()
        )

        assert result["raw_spreadsheet"] == SPREADSHEET
        assert result["drive_url"] == DRIVE_URL
        assert len(result["schema_mapping"]) == 1
        assert len(result["image_metadata"]) == 1
        assert len(result["classification_results"]) == 1
        assert result["updated_spreadsheet"] == {"stub": True, "source": SPREADSHEET}
        assert result["error_trace"] == []  # happy path never triggers retry/manual_review

    def test_checkpoint_file_is_created_on_disk(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        assert not db_path.exists()
        run_pipeline(SPREADSHEET, DRIVE_URL, db_path=db_path, thread_id=_thread_id())
        assert db_path.exists()
        # it's a real sqlite db, not just an empty file
        conn = sqlite3.connect(str(db_path))
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "checkpoints" in tables

    def test_checkpoint_is_saved_per_node(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        thread_id = _thread_id()
        run_pipeline(SPREADSHEET, DRIVE_URL, db_path=db_path, thread_id=thread_id)
        with _sqlite_checkpointer(db_path) as checkpointer:
            checkpoints = list(checkpointer.list({"configurable": {"thread_id": thread_id}}))
        # one per superstep: __start__, schema_matching, drive_crawler,
        # vision_classification, tabular_update, finalization (at least)
        assert len(checkpoints) >= 6

    def test_threads_do_not_leak_into_each_other(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        run_pipeline(SPREADSHEET, DRIVE_URL, db_path=db_path, thread_id="thread-a")
        run_pipeline("other.xlsx", "https://drive/other", db_path=db_path, thread_id="thread-b")

        with _sqlite_checkpointer(db_path) as checkpointer:
            state_a = checkpointer.get({"configurable": {"thread_id": "thread-a"}})
            state_b = checkpointer.get({"configurable": {"thread_id": "thread-b"}})

        assert state_a["channel_values"]["raw_spreadsheet"] == SPREADSHEET
        assert state_b["channel_values"]["raw_spreadsheet"] == "other.xlsx"


class TestResume:
    def test_interrupted_run_is_missing_downstream_state(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        partial = run_pipeline(
            SPREADSHEET,
            DRIVE_URL,
            db_path=db_path,
            thread_id=_thread_id(),
            interrupt_after=["drive_crawler"],
        )
        assert "image_metadata" in partial
        assert "classification_results" not in partial
        assert "updated_spreadsheet" not in partial

    def test_resume_completes_pipeline_from_checkpoint(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        thread_id = _thread_id()
        partial = run_pipeline(
            SPREADSHEET,
            DRIVE_URL,
            db_path=db_path,
            thread_id=thread_id,
            interrupt_after=["drive_crawler"],
        )

        final = resume_pipeline(db_path=db_path, thread_id=thread_id)

        assert "classification_results" in final
        assert "updated_spreadsheet" in final
        # state carried over from before the interrupt, not recomputed
        assert final["image_metadata"] == partial["image_metadata"]
        assert final["schema_mapping"] == partial["schema_mapping"]
        assert final["raw_spreadsheet"] == SPREADSHEET

    def test_resume_adds_checkpoints_on_top_of_the_interrupted_ones(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        thread_id = _thread_id()
        run_pipeline(
            SPREADSHEET,
            DRIVE_URL,
            db_path=db_path,
            thread_id=thread_id,
            interrupt_after=["drive_crawler"],
        )
        with _sqlite_checkpointer(db_path) as checkpointer:
            before = len(list(checkpointer.list({"configurable": {"thread_id": thread_id}})))

        resume_pipeline(db_path=db_path, thread_id=thread_id)
        with _sqlite_checkpointer(db_path) as checkpointer:
            after = len(list(checkpointer.list({"configurable": {"thread_id": thread_id}})))

        assert after > before

    def test_resuming_a_thread_with_no_checkpoint_fails_loudly(self, tmp_path):
        db_path = tmp_path / "checkpoints.sqlite"
        with pytest.raises(EmptyInputError):
            resume_pipeline(db_path=db_path, thread_id=_thread_id())
