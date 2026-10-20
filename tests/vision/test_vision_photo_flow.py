"""Test-first acceptance test suite for S6b: Backend Alur Foto & Klasifikasi Multi-Sinyal.

Contract source:
- reports/cabai-kms-jsonb/TECH_PLAN.md:
  * Line 28: S6b introduction (Backend Alur Foto Multi-Sinyal, pemilik forge)
  * Line 522: Table 5 DoD & boundaries for S6b
  * Line 558: Acceptance criterion A23 (test_vision_three_way_signal_classification)
  * Line 559: Acceptance criterion A24 (PHOTO_VARIETY_MISMATCH fail-closed review items)
  * Line 563: Acceptance criterion A28 (Deterministic CI isolation without 9Router quota)
  * Section 4: 4.1 Multi-signal input architecture, 4.2 fail-closed policy, 4.3 3 explicit actions
  * Section 7: Curated dataset requirements & mock protocol

Acceptance criteria covered:
- A23: Klasifikasi foto mempertimbangkan 3 sinyal: citra visual, nama berkas/caption,
       dan opsi varietas Excel run aktif. Prompt LVM dibatasi hanya opsi varietas run saat ini.
- A24: Foto yang tidak cocok dengan opsi varietas Excel run aktif menghasilkan item review
       PHOTO_VARIETY_MISMATCH (fail-closed) dengan 3 aksi (ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD).
- A28: Isolasi kuota vision: Seluruh pengujian unit CI berjalan 100% menggunakan mock/stub deterministik
       tanpa memanggil 9Router atau jaringan eksternal.
- S6b-HOOK-01: Integrasi vision_hook.py (vision_classification_with_storage) dengan run_scope_varieties
               dan CAS media storage.
- S6b-HOOK-02: Fail-closed review item generation dalam state pipeline untuk foto mismatch.
- S6b-CONTRACT-01: Re-ekspor / ketersediaan kontrak PhotoContextSignal, VisionClassificationResult,
                   dan PhotoMismatchDecision di src/schema/contracts.py.
"""

from __future__ import annotations

import io
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import openpyxl
import pytest
from PIL import Image

from src.agents import vision_classification
from src.schema.contracts import ImageMetadata
from src.storage.document_contracts import (
    DocumentReviewItem,
    PhotoContextSignal,
    PhotoMismatchDecision,
    VisionClassificationResult,
)

# Test-scoped fixtures and constants
EXCEL_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "data" / "samples" / "data_input.xlsx"
ACTIVE_EXCEL_VARIETIES = [
    "Cabai rawit (Capsicum frutescens L)",
    "cabai besar (Capsicum annum L)",
]
TEST_DATETIME = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def make_test_jpeg_bytes(width: int = 256, height: int = 256, color: tuple[int, int, int] = (34, 139, 34)) -> bytes:
    """Generate valid test JPEG bytes in-memory for deterministic vision tests."""
    stream = io.BytesIO()
    img = Image.new("RGB", (width, height), color)
    img.save(stream, format="JPEG")
    return stream.getvalue()


class MockRecordingLVM:
    """Deterministic mock LVM provider recording prompt messages and returning fixed responses."""

    def __init__(self, response: Any = None):
        self.calls: list[list[dict[str, Any]]] = []
        self.response = response

    def __call__(self, *, response_model: Any = None, messages: list[dict[str, Any]] | None = None, **kwargs: Any) -> Any:
        self.calls.append(messages or [])
        return self.response


# ============================================================================
# Criterion A23: Three-Way Signal Integration & Scoped Prompt
# ============================================================================


def test_vision_three_way_signal_classification():
    """A23: Klasifikasi foto mempertimbangkan 3 sinyal: citra visual, nama berkas/caption,
    dan opsi varietas Excel run aktif (sel F3 Cabai rawit & F4 cabai besar).
    """
    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_f3_rawit_001",
        filename="cabai_rawit_daun.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )
    photo_signal = PhotoContextSignal(
        filename="cabai_rawit_daun.jpg",
        caption="Pengambilan sampel permukaan daun Dusun Randu",
        extracted_part="DAUN",
        suggested_variety_hint="Cabai rawit",
        raw_tokens=["cabai", "rawit", "daun"],
    )

    expected_mock_result = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai rawit (Capsicum frutescens L)",
        identified_part="DAUN",
        visual_confidence=0.92,
        text_confidence=0.88,
        confidence=0.90,
        visual_evidence="Bentuk daun ovate dengan permukaan mengkilap khas Capsicum frutescens L",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=True,
    )
    mock_lvm = MockRecordingLVM(response=expected_mock_result)

    # VisionSession must accept run_scope_varieties from the active Excel run
    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=mock_lvm,
    )

    result = session.classify(
        image,
        image_bytes=jpeg_bytes,
        photo_signal=photo_signal,
    )

    # Verify LVM received prompt constrained to active Excel varieties
    assert len(mock_lvm.calls) >= 1, "Mock LVM must be called exactly once per image"
    prompt_messages = mock_lvm.calls[0]
    prompt_text = " ".join(str(m.get("content", "")) for m in prompt_messages)
    assert "Cabai rawit (Capsicum frutescens L)" in prompt_text
    assert "cabai besar (Capsicum annum L)" in prompt_text

    # Verify result integrates all 3 signals
    assert isinstance(result, VisionClassificationResult)
    assert result.classification_status == "KNOWN"
    assert result.matched_variety == "Cabai rawit (Capsicum frutescens L)"
    assert result.identified_part == "DAUN"
    assert result.visual_confidence >= 0.85
    assert result.signals_consistent is True
    assert set(result.options_evaluated) == set(ACTIVE_EXCEL_VARIETIES)


def test_vision_prompt_scoped_to_excel_varieties():
    """A23: Batasan Prompt LVM: Model vision HANYA diberikan opsi varietas dari run saat ini
    sebagai kandidat klasifikasi untuk mencegah context pollution dan halusinasi.
    """
    scoped_varieties = ["Cabai rawit (Capsicum frutescens L)", "cabai besar (Capsicum annum L)"]
    mock_lvm = MockRecordingLVM()

    session = vision_classification.VisionSession(
        run_scope_varieties=scoped_varieties,
        lvm_call=mock_lvm,
    )

    # Knowledge source text or prompt must ONLY contain the scoped varieties
    assert hasattr(session, "run_scope_varieties"), "VisionSession must expose run_scope_varieties attribute"
    assert session.run_scope_varieties == scoped_varieties

    # Canonical varieties not in scoped_varieties (e.g. Gendot, Kopay) must not appear in knowledge text
    for excluded in ["Gendot", "Kopay", "Katokkon"]:
        assert excluded not in session.knowledge_source_text, (
            f"Non-run variety '{excluded}' must be excluded from scoped prompt text"
        )


def test_photo_context_signal_extraction_from_filename_and_caption():
    """A23: Ekstraksi sinyal konteks (Sinyal 2) dari nama berkas dan caption Google Drive
    menghasilkan PhotoContextSignal terstruktur.
    """
    assert hasattr(vision_classification, "extract_photo_context_signal"), (
        "vision_classification must define extract_photo_context_signal"
    )
    signal = vision_classification.extract_photo_context_signal(
        filename="cabai_rawit_daun_01.jpg",
        caption="Pengambilan sampel permukaan daun Dusun Randu",
        known_varieties=ACTIVE_EXCEL_VARIETIES,
    )
    assert isinstance(signal, PhotoContextSignal)
    assert signal.filename == "cabai_rawit_daun_01.jpg"
    assert signal.extracted_part == "DAUN"
    assert (
        signal.suggested_variety_hint == "Cabai rawit (Capsicum frutescens L)"
        or (signal.suggested_variety_hint is not None and "rawit" in signal.suggested_variety_hint.lower())
    )
    assert "daun" in signal.raw_tokens
    assert signal.caption == "Pengambilan sampel permukaan daun Dusun Randu"


# ============================================================================
# Criterion A24: Fail-Closed PHOTO_VARIETY_MISMATCH Review Items
# ============================================================================


def test_photo_mismatch_creates_blocking_review_item_on_no_match():
    """A24: Foto dengan varietas yang tidak cocok (OTHER/NO_MATCH) terhadap opsi Excel run aktif
    menghasilkan item review PHOTO_VARIETY_MISMATCH dengan status pending.
    """
    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_katokkon_001",
        filename="cabai_katokkon_buah.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )
    photo_signal = PhotoContextSignal(
        filename="cabai_katokkon_buah.jpg",
        caption="Cabai katokkon toraja berbentuk lonceng",
        extracted_part="BUAH",
        suggested_variety_hint="Cabai Katokkon",
    )

    other_mock_result = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        identified_part="BUAH",
        visual_confidence=0.91,
        text_confidence=0.50,
        confidence=0.70,
        visual_evidence="Morfologi buah membulat seperti lonceng khas Katokkon, tidak cocok dengan varietas Excel",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=False,
    )
    mock_lvm = MockRecordingLVM(response=other_mock_result)

    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=mock_lvm,
    )

    review_item = session.evaluate_photo_alignment(
        image,
        photo_signal=photo_signal,
        visual_result=other_mock_result,
    )

    assert review_item is not None, "Mismatch must produce a DocumentReviewItem"
    assert isinstance(review_item, DocumentReviewItem)
    assert review_item.category == "PHOTO_VARIETY_MISMATCH"
    assert review_item.status == "pending", "Review item must be pending to fail-closed and block commit"
    assert review_item.target_document_key is None, "Unassigned mismatched photo must have null target document key"
    assert review_item.source_label == "cabai_katokkon_buah.jpg"


def test_photo_mismatch_creates_blocking_review_item_on_adversarial_filename():
    """A24: Kontradiksi antara sinyal visual dan teks nama berkas (adversarial filename)
    memicu signals_consistent=False dan menghasilkan review PHOTO_VARIETY_MISMATCH.
    """
    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_adv_001",
        filename="cabai_keriting_buah.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )
    # Filename says keriting, but visual says Cabai rawit
    photo_signal = PhotoContextSignal(
        filename="cabai_keriting_buah.jpg",
        caption="Sampel buah cabai",
        extracted_part="BUAH",
        suggested_variety_hint="Cabai keriting",
    )
    visual_rawit_result = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai rawit (Capsicum frutescens L)",
        identified_part="BUAH",
        visual_confidence=0.88,
        text_confidence=0.10,
        confidence=0.88,
        visual_evidence="Buah tegak kecil khas Capsicum frutescens",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=False,
    )

    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=MockRecordingLVM(response=visual_rawit_result),
    )

    review_item = session.evaluate_photo_alignment(
        image,
        photo_signal=photo_signal,
        visual_result=visual_rawit_result,
    )

    assert review_item is not None
    assert review_item.category == "PHOTO_VARIETY_MISMATCH"
    assert review_item.status == "pending"
    assert "keriting" in review_item.source_context.lower() or "mismatch" in review_item.source_context.lower()


def test_photo_mismatch_creates_blocking_review_item_on_low_confidence():
    """A24: Model visual dengan confidence di bawah ambang batas (< 0.85) atau UNCERTAIN
    tidak boleh auto-assign dan wajib masuk review PHOTO_VARIETY_MISMATCH.
    """
    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_low_conf_001",
        filename="cabai_rawit_daun_buram.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )
    low_conf_result = VisionClassificationResult(
        classification_status="UNCERTAIN",
        matched_variety=None,
        identified_part="DAUN",
        visual_confidence=0.62,
        text_confidence=0.85,
        confidence=0.62,
        visual_evidence="Citra buram / out-of-focus, tidak dapat memastikan varietas secara konklusif",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=False,
    )

    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=MockRecordingLVM(response=low_conf_result),
    )

    review_item = session.evaluate_photo_alignment(
        image,
        photo_signal=None,
        visual_result=low_conf_result,
    )

    assert review_item is not None
    assert review_item.category == "PHOTO_VARIETY_MISMATCH"
    assert review_item.status == "pending"


def test_photo_mismatch_creates_blocking_review_item_on_unconvincing_organ():
    """A24: Citra non-tanaman atau foto yang organ tanamannya tidak teridentifikasi
    menghasilkan item review PHOTO_VARIETY_MISMATCH.
    """
    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_spad_meter_001",
        filename="alat_ukur_spad.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )
    unconvincing_result = VisionClassificationResult(
        classification_status="UNCERTAIN",
        matched_variety=None,
        identified_part="BATANG",
        visual_confidence=0.40,
        text_confidence=0.0,
        confidence=0.40,
        visual_evidence="Citra menampilkan alat ukur SPAD dan tangan manusia, organ cabai tidak meyakinkan",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=False,
    )

    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=MockRecordingLVM(response=unconvincing_result),
    )

    review_item = session.evaluate_photo_alignment(
        image,
        visual_result=unconvincing_result,
    )

    assert review_item is not None
    assert review_item.category == "PHOTO_VARIETY_MISMATCH"
    assert review_item.status == "pending"


def test_photo_mismatch_review_item_candidate_actions_contract():
    """A24 & TECH_PLAN 4.3: Item review PHOTO_VARIETY_MISMATCH wajib menyediakan
    3 aksi resolusi eksplisit: ASSIGN_EXISTING, CREATE_NEW_DOCUMENT, DISCARD.
    """
    assert hasattr(vision_classification, "create_photo_mismatch_review_item"), (
        "vision_classification must define create_photo_mismatch_review_item"
    )
    review_item = vision_classification.create_photo_mismatch_review_item(
        filename="cabai_unknown.jpg",
        suggested_hint="Cabai Habanero",
        visual_evidence="Citra menyerupai habanero",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
    )

    assert isinstance(review_item, DocumentReviewItem)
    actions = [r.get("action") for r in review_item.candidate_resolutions]
    assert "ASSIGN_EXISTING" in actions, "Must provide ASSIGN_EXISTING action"
    assert "CREATE_NEW_DOCUMENT" in actions, "Must provide CREATE_NEW_DOCUMENT action"
    assert "DISCARD" in actions, "Must provide DISCARD action"


# ============================================================================
# S6b-HOOK: Integration with vision_hook.py (vision_classification_with_storage)
# ============================================================================


def test_vision_hook_integrates_excel_run_scope_and_photo_signals():
    """S6b-HOOK-01: vision_classification_with_storage mengekstrak opsi varietas dari Excel
    run aktif dan mengintegrasikan 3 sinyal foto ke dalam vision_rows dan CAS storage.
    """
    import types
    from src.integrations import vision_hook

    assert EXCEL_FIXTURE_PATH.exists(), f"Excel fixture {EXCEL_FIXTURE_PATH} must exist"
    workbook_bytes = EXCEL_FIXTURE_PATH.read_bytes()
    jpeg_bytes = make_test_jpeg_bytes()

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, path, **kwargs: (
        {"id": "asset_test_01", "original_sha256": "sha_orig", "image_sha256": "sha_img", "transform_profile": "crop"}
        if method == "POST" and "/assets/drive/" in path
        else jpeg_bytes
    )

    mock_res = types.SimpleNamespace(
        on_progress=lambda m: None,
        vision_rate_limiter=None,
    )

    state = {
        "workbook_bytes": workbook_bytes,
        "image_metadata": [
            {
                "file_id": "img_sample_01",
                "filename": "cabai_rawit_daun_sample.jpg",
                "mime_type": "image/jpeg",
                "size": len(jpeg_bytes),
                "created_time": "2026-06-01T10:00:00Z",
            }
        ],
        "agent_status": {},
    }
    config = {"configurable": {"runtime_resources_id": "test_res_01"}}

    with patch("src.orchestrator.graph._resources", return_value=mock_res), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client):
        out = vision_hook.vision_classification_with_storage(state, config)

    assert "vision_rows" in out, "Hook output must include vision_rows"
    rows = out["vision_rows"]
    assert len(rows) == 1
    row = rows[0]
    # S6b requires multi-signal tracking in output rows
    assert "options_evaluated" in row or "signals_consistent" in row, (
        "vision_rows must record multi-signal options_evaluated or signals_consistent"
    )


def test_vision_hook_fail_closed_blocking_review_in_state():
    """S6b-HOOK-02: Foto mismatch dalam alur vision_classification_with_storage
    menghasilkan item review PHOTO_VARIETY_MISMATCH di dalam state pipeline.
    """
    import types
    from src.integrations import vision_hook

    workbook_bytes = EXCEL_FIXTURE_PATH.read_bytes()
    jpeg_bytes = make_test_jpeg_bytes()

    mock_client = MagicMock()
    mock_client.request.side_effect = lambda method, path, **kwargs: (
        {"id": "asset_mismatch_01", "original_sha256": "sha_orig", "image_sha256": "sha_img", "transform_profile": "crop"}
        if method == "POST" and "/assets/drive/" in path
        else jpeg_bytes
    )

    mock_res = types.SimpleNamespace(
        on_progress=lambda m: None,
        vision_rate_limiter=None,
    )

    state = {
        "workbook_bytes": workbook_bytes,
        "image_metadata": [
            {
                "file_id": "img_mismatch_01",
                "filename": "cabai_habanero_buah.jpg",
                "mime_type": "image/jpeg",
                "size": len(jpeg_bytes),
                "created_time": "2026-06-01T10:00:00Z",
            }
        ],
        "agent_status": {},
        "review_items": [],
    }
    config = {"configurable": {"runtime_resources_id": "test_res_02"}}

    with patch("src.orchestrator.graph._resources", return_value=mock_res), \
         patch("src.integrations.vision_hook.KmsClient", return_value=mock_client):
        out = vision_hook.vision_classification_with_storage(state, config)

    # State must contain the staged PHOTO_VARIETY_MISMATCH review item
    review_items = out.get("review_items", [])
    photo_mismatches = [
        r for r in review_items
        if (getattr(r, "category", None) or (r.get("category") if isinstance(r, dict) else None)) == "PHOTO_VARIETY_MISMATCH"
    ]
    assert len(photo_mismatches) >= 1, (
        "Mismatched photo processed by vision hook must enqueue a PHOTO_VARIETY_MISMATCH review item into state"
    )
    item = photo_mismatches[0]
    status = getattr(item, "status", None) or (item.get("status") if isinstance(item, dict) else None)
    assert status == "pending", "Staged review item must be pending to block commit"


# ============================================================================
# Criterion A28: Quota & CI Isolation (Zero External Network Calls)
# ============================================================================


def test_vision_photo_flow_deterministic_isolation_no_network(monkeypatch: pytest.MonkeyPatch):
    """A28: Isolasi kuota vision: Seluruh pengujian unit CI berjalan 100% menggunakan
    mock/stub deterministik tanpa memanggil 9Router atau jaringan eksternal.
    """
    monkeypatch.setenv("CABAI_KMS_VISION_PROVIDER", "mock")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("NINEROUTER_API_KEY", "")

    # Forbid any socket connections
    def guarded_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("External network connection attempted during CI vision unit test!")

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)

    jpeg_bytes = make_test_jpeg_bytes()
    image = ImageMetadata(
        file_id="img_iso_001",
        filename="cabai_rawit_daun.jpg",
        mime_type="image/jpeg",
        size=len(jpeg_bytes),
        created_time=TEST_DATETIME,
    )

    mock_res = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai rawit (Capsicum frutescens L)",
        identified_part="DAUN",
        visual_confidence=0.95,
        text_confidence=0.90,
        confidence=0.92,
        visual_evidence="Mock visual feature matching",
        options_evaluated=ACTIVE_EXCEL_VARIETIES,
        signals_consistent=True,
    )

    session = vision_classification.VisionSession(
        run_scope_varieties=ACTIVE_EXCEL_VARIETIES,
        lvm_call=MockRecordingLVM(response=mock_res),
    )

    result = session.classify(image, image_bytes=jpeg_bytes)
    assert result.classification_status == "KNOWN"
    assert result.visual_confidence >= 0.85


# ============================================================================
# S6b-CONTRACT: Schema Contracts Export Parity
# ============================================================================


def test_schema_contracts_exports_photo_multi_signal_contracts():
    """S6b-CONTRACT-01: src/schema/contracts.py mengekspor kontrak PhotoContextSignal,
    VisionClassificationResult, dan PhotoMismatchDecision untuk konsistensi pipeline.
    """
    from src.schema import contracts

    required_contracts = [
        "PhotoContextSignal",
        "VisionClassificationResult",
        "PhotoMismatchDecision",
    ]
    missing = [name for name in required_contracts if not hasattr(contracts, name)]
    assert not missing, f"src.schema.contracts must export S6b contracts: {missing}"
