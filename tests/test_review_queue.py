from __future__ import annotations

import pytest

from src.agents.schema_matching import review_queue as rq
from src.schema.contracts import NULL_ROW, SchemaMapping


def _mapping(target_row: str, confidence: float, attribute: str = "x") -> SchemaMapping:
    return SchemaMapping(
        source_attribute=attribute,
        source_format="row-oriented",
        target_canonical_row=target_row,
        confidence=confidence,
        reasoning="test fixture",
        normalization_required=False,
    )


@pytest.fixture
def queue_path(tmp_path):
    return tmp_path / "review.jsonl"


class TestNeedsReview:
    def test_null_target_needs_review_regardless_of_confidence(self):
        mapping = _mapping(NULL_ROW, confidence=0.99)
        assert rq.needs_review(mapping) is True

    def test_low_confidence_needs_review(self):
        mapping = _mapping("r_1", confidence=0.4)
        assert rq.needs_review(mapping, confidence_threshold=0.6) is True

    def test_confident_non_null_does_not_need_review(self):
        mapping = _mapping("r_1", confidence=0.95)
        assert rq.needs_review(mapping, confidence_threshold=0.6) is False

    def test_threshold_is_configurable(self):
        mapping = _mapping("r_1", confidence=0.7)
        assert rq.needs_review(mapping, confidence_threshold=0.6) is False
        assert rq.needs_review(mapping, confidence_threshold=0.8) is True


class TestSubmitForReview:
    def test_returns_none_when_no_review_needed(self, queue_path):
        mapping = _mapping("r_1", confidence=0.95)
        result = rq.submit_for_review(mapping, queue_path=queue_path)
        assert result is None
        assert not queue_path.exists()

    def test_enqueues_when_review_needed(self, queue_path):
        mapping = _mapping(NULL_ROW, confidence=0.9)
        item = rq.submit_for_review(mapping, queue_path=queue_path)
        assert item is not None
        assert item.status == "pending"
        assert queue_path.exists()

    def test_reason_mentions_null_target(self, queue_path):
        mapping = _mapping(NULL_ROW, confidence=0.9, attribute="Nama Kolektor")
        item = rq.submit_for_review(mapping, queue_path=queue_path)
        assert "Nama Kolektor" in item.reason
        assert "NULL" in item.reason

    def test_reason_mentions_low_confidence(self, queue_path):
        mapping = _mapping("r_3", confidence=0.3, attribute="Suhu")
        item = rq.submit_for_review(mapping, confidence_threshold=0.6, queue_path=queue_path)
        assert "Suhu" in item.reason
        assert "0.3" in item.reason or "confidence" in item.reason.lower()


class TestProcessMapping:
    def test_patches_error_trace_when_review_needed(self, queue_path):
        state = {"error_trace": ["prior issue"]}
        mapping = _mapping(NULL_ROW, confidence=0.9)
        patch = rq.process_mapping(mapping, state, queue_path=queue_path)
        assert "error_trace" in patch
        assert patch["error_trace"][0] == "prior issue"  # existing trace preserved
        assert len(patch["error_trace"]) == 2

    def test_empty_patch_when_no_review_needed(self, queue_path):
        state = {"error_trace": []}
        mapping = _mapping("r_1", confidence=0.95)
        patch = rq.process_mapping(mapping, state, queue_path=queue_path)
        assert patch == {}

    def test_does_not_mutate_original_state(self, queue_path):
        state = {"error_trace": ["a"]}
        mapping = _mapping(NULL_ROW, confidence=0.9)
        rq.process_mapping(mapping, state, queue_path=queue_path)
        assert state["error_trace"] == ["a"]  # unchanged — patch is a new list


class TestHumanReviewApi:
    def test_list_pending_reflects_enqueued_items(self, queue_path):
        rq.enqueue(_mapping(NULL_ROW, 0.9), reason="r1", queue_path=queue_path)
        rq.enqueue(_mapping(NULL_ROW, 0.9), reason="r2", queue_path=queue_path)
        pending = rq.list_pending(queue_path=queue_path)
        assert len(pending) == 2

    def test_approve_marks_item_resolved_and_removes_from_pending(self, queue_path):
        item = rq.enqueue(_mapping(NULL_ROW, 0.9), reason="r1", queue_path=queue_path)
        approved = rq.approve(item.item_id, resolved_by="reviewer-1", queue_path=queue_path)
        assert approved.status == "approved"
        assert approved.resolved_by == "reviewer-1"
        assert approved.mapping.target_canonical_row == NULL_ROW  # unchanged
        assert rq.list_pending(queue_path=queue_path) == []

    def test_revise_replaces_mapping_and_removes_from_pending(self, queue_path):
        item = rq.enqueue(_mapping(NULL_ROW, 0.9, attribute="y"), reason="r1", queue_path=queue_path)
        corrected = _mapping("r_5", 0.9, attribute="y")
        revised = rq.revise(item.item_id, corrected, resolved_by="reviewer-1", queue_path=queue_path)
        assert revised.status == "revised"
        assert revised.mapping.target_canonical_row == "r_5"
        assert rq.list_pending(queue_path=queue_path) == []

    def test_approving_unknown_id_raises_keyerror(self, queue_path):
        with pytest.raises(KeyError):
            rq.approve("does-not-exist", queue_path=queue_path)

    def test_approving_already_resolved_item_raises(self, queue_path):
        item = rq.enqueue(_mapping(NULL_ROW, 0.9), reason="r1", queue_path=queue_path)
        rq.approve(item.item_id, queue_path=queue_path)
        with pytest.raises(ValueError):
            rq.approve(item.item_id, queue_path=queue_path)

    def test_queue_file_is_append_only_jsonl(self, queue_path):
        item = rq.enqueue(_mapping(NULL_ROW, 0.9), reason="r1", queue_path=queue_path)
        rq.approve(item.item_id, queue_path=queue_path)
        lines = queue_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 2  # enqueue + approve, neither line rewritten
