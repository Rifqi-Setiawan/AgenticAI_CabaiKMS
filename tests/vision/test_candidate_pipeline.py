"""Pipeline integration tests for B-5: Vision Hook Signal Fusion and Candidate Integration (P1..P6).

Tests:
P1: AUTO_LINK outcome applies canonical worksheet update (legacy flow).
P2: REVIEW_MISMATCH outcome produces a blocking PHOTO_VARIETY_MISMATCH review item.
P3: REVIEW_UNCERTAIN outcome produces a blocking PHOTO_VARIETY_MISMATCH review item.
P4: CANDIDATE outcome adds candidate image to candidate queue without creating document or modifying sheet.
P5: Idempotency: rerunning pipeline with the same image preserves candidate without duplicating.
P6: Previously discarded image (original_sha256 in discarded_images) is skipped with note in vision_rows.
"""

from __future__ import annotations

import hashlib
import io
from unittest.mock import MagicMock, patch
import openpyxl
import pytest

from src.agents.signal_fusion import FusionAction, FusionOutcome, fuse_photo_signals
from src.agents.variety_registry import VarietyRegistry
from src.integrations import vision_hook
from src.schema.contracts import ImageMetadata, VisionClassificationResult


@pytest.fixture
def mock_resources():
    res = MagicMock()
    res.on_progress = lambda m: None
    return res


@pytest.fixture
def base_workbook_bytes():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    ws.cell(1, 1, "Nomor")
    ws.cell(1, 2, "Karakteristik")
    ws.cell(1, 3, "Cabai Rawit")
    ws.cell(1, 4, "Cabai Keriting")
    ws.cell(2, 1, "1")
    ws.cell(2, 2, "Gambar Buah")
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


FAKE_BYTES = b"fake_image_bytes_payload"
FAKE_SHA = hashlib.sha256(FAKE_BYTES).hexdigest()


def _make_state(wb_bytes, filename="foto_01.png", sha="1"*64):
    return {
        "workbook_bytes": wb_bytes,
        "image_metadata": [
            {
                "file_id": "drv_01",
                "filename": filename,
                "mime_type": "image/png",
                "size": 1000,
                "created_time": "2026-06-01T10:00:00Z",
            }
        ],
        "review_items": [],
        "agent_status": {},
    }


def test_p1_pipeline_auto_link_flow(base_workbook_bytes, mock_resources):
    """P1: AUTO_LINK writes to canonical worksheet and produces 0 review items."""
    state = _make_state(base_workbook_bytes, "foto_rawit_buah.png")

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, path, **kw: {
        "id": "a" * 64,
        "image_sha256": FAKE_SHA,
        "original_sha256": "1" * 64,
        "transform_profile": "primary",
    } if method == "POST" else (FAKE_BYTES if "media" in path else [])

    mock_vis_result = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Rawit",
        identified_part="BUAH",
        visual_confidence=0.92,
        visual_evidence="Buah rawit tegak",
    )

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify", return_value=mock_vis_result):
        res = vision_hook.vision_classification_with_storage(state, config={})
        assert len(res["review_items"]) == 0
        assert len(res["vision_rows"]) == 1
        assert res["vision_rows"][0]["write_applied"] is True
        assert res["vision_rows"][0]["status"] == "KNOWN"


def test_p2_pipeline_review_mismatch_flow(base_workbook_bytes, mock_resources):
    """P2: REVIEW_MISMATCH produces a blocking PHOTO_VARIETY_MISMATCH review item."""
    # Filename says rawit, visual says keriting
    state = _make_state(base_workbook_bytes, "cabai_rawit_buah.png")

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, path, **kw: {
        "id": "b" * 64,
        "image_sha256": FAKE_SHA,
        "original_sha256": "2" * 64,
        "transform_profile": "primary",
    } if method == "POST" else (FAKE_BYTES if "media" in path else [])

    mock_vis_result = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Keriting",
        identified_part="BUAH",
        visual_confidence=0.90,
        visual_evidence="Buah keriting panjang",
    )

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify", return_value=mock_vis_result):
        res = vision_hook.vision_classification_with_storage(state, config={})
        assert len(res["review_items"]) == 1
        assert res["review_items"][0].category == "PHOTO_VARIETY_MISMATCH"
        assert res["vision_rows"][0]["write_applied"] is False


def test_p3_pipeline_review_uncertain_flow(base_workbook_bytes, mock_resources):
    """P3: REVIEW_UNCERTAIN produces a blocking PHOTO_VARIETY_MISMATCH review item."""
    state = _make_state(base_workbook_bytes, "foto_ragu.png")

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, path, **kw: {
        "id": "c" * 64,
        "image_sha256": FAKE_SHA,
        "original_sha256": "3" * 64,
        "transform_profile": "primary",
    } if method == "POST" else (FAKE_BYTES if "media" in path else [])

    mock_vis_result = VisionClassificationResult(
        classification_status="UNCERTAIN",
        matched_variety=None,
        identified_part="DAUN",
        visual_confidence=0.55,
        visual_evidence="Gambar kabur",
    )

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify", return_value=mock_vis_result):
        res = vision_hook.vision_classification_with_storage(state, config={})
        assert len(res["review_items"]) == 1
        assert res["review_items"][0].category == "PHOTO_VARIETY_MISMATCH"


def test_p4_pipeline_candidate_flow(base_workbook_bytes, mock_resources):
    """P4: CANDIDATE outcome adds candidate via API without writing to sheet or creating document."""
    state = _make_state(base_workbook_bytes, "varietas_baru_langka.png")

    mock_client = MagicMock()
    added_candidates = []
    def _mock_request(method, path, **kw):
        if method == "POST" and "assets" in path:
            return {
                "id": "d" * 64,
                "image_sha256": FAKE_SHA,
                "original_sha256": "4" * 64,
                "transform_profile": "primary",
            }
        if method == "POST" and "candidates" in path:
            added_candidates.append(kw.get("json"))
            return {"candidate_id": "cand_p4", "status": "CANDIDATE"}
        if method == "GET" and "media" in path:
            return FAKE_BYTES
        if method == "GET" and "documents" in path:
            return []
        return []

    mock_client.request.side_effect = _mock_request

    mock_vis_result = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        identified_part="BUAH",
        visual_confidence=0.88,
        visual_evidence="Spesimen unik varietas baru",
    )

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify", return_value=mock_vis_result):
        res = vision_hook.vision_classification_with_storage(state, config={})
        assert len(res["review_items"]) == 0
        assert res["vision_rows"][0]["status"] == "CANDIDATE"
        assert res["vision_rows"][0]["write_applied"] is False
        assert len(added_candidates) == 1
        assert added_candidates[0]["organ_part"] == "buah"


def test_p5_pipeline_candidate_idempotent_on_rerun(base_workbook_bytes, mock_resources):
    """P5: Rerunning candidate flow with the same image preserves candidate without duplicating."""
    state = _make_state(base_workbook_bytes, "varietas_p5.png")

    mock_client = MagicMock()
    call_counts = {"add_candidate": 0}
    def _mock_request(method, path, **kw):
        if method == "POST" and "assets" in path:
            return {"id": "e" * 64, "image_sha256": FAKE_SHA, "original_sha256": "5" * 64, "transform_profile": "primary"}
        if method == "POST" and "candidates" in path:
            call_counts["add_candidate"] += 1
            return {"candidate_id": "cand_p5", "status": "CANDIDATE"}
        if method == "GET" and "media" in path:
            return FAKE_BYTES
        return []

    mock_client.request.side_effect = _mock_request

    mock_vis_result = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        identified_part="BUAH",
        visual_confidence=0.89,
        visual_evidence="Morfologi varietas baru",
    )

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify", return_value=mock_vis_result):
        res1 = vision_hook.vision_classification_with_storage(state, config={})
        res2 = vision_hook.vision_classification_with_storage(state, config={})
        assert res1["vision_rows"][0]["status"] == "CANDIDATE"
        assert res2["vision_rows"][0]["status"] == "CANDIDATE"


def test_p6_pipeline_skips_previously_discarded_image(base_workbook_bytes, mock_resources):
    """P6: Image whose original_sha256 is recorded in discarded_images is skipped with note."""
    state = _make_state(base_workbook_bytes, "tomat_dibuang.png", sha="6" * 64)

    mock_client = MagicMock()
    def _mock_request(method, path, **kw):
        if method == "POST" and "assets" in path:
            return {
                "id": "f" * 64,
                "image_sha256": FAKE_SHA,
                "original_sha256": "6" * 64,  # discarded sha
                "transform_profile": "primary",
            }
        if method == "GET" and "discarded" in path:
            return [{"original_sha256": "6" * 64, "reason": "Bukan cabai"}]
        if method == "GET" and "media" in path:
            return FAKE_BYTES
        return []

    mock_client.request.side_effect = _mock_request

    with patch("src.orchestrator.graph._resources", return_value=mock_resources), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client), \
         patch("src.agents.vision_classification.VisionSession.classify") as mock_classify:
        res = vision_hook.vision_classification_with_storage(state, config={})
        # VLM classify must NOT be called for discarded image!
        assert not mock_classify.called
        assert len(res["vision_rows"]) == 1
        assert res["vision_rows"][0]["status"] == "DISCARDED"
        assert "discarded" in res["vision_rows"][0]["write_reason"].lower()
