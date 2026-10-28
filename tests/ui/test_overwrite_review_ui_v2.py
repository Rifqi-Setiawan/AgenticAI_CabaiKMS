"""Unit tests for L2: UI categorized review queue rendering and user input validation (U-01..U-05).

Tests:
U-01: No hardcoded reason strings in decision payload; empty/too short reason (<10 chars) -> no API call made.
U-02: 'Koreksi' sends corrected_value and corrected_unit from user input, not synthetic hardcodes.
U-03: UNIT_MISMATCH does NOT display 'Terapkan Baru' button (only 'Pertahankan Lama' and 'Koreksi').
U-04: Scenario '85 kg vs 80 cm': without explicit unit confirmation, 'Koreksi' does not send '85 cm'.
U-05: Other categories (e.g. NEW_ATTRIBUTE) retain default 2-button (Approve/Reject) controls.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from src.integrations import streamlit_commit
from src.storage.document_contracts import (
    CurrentSourceReference,
    DocumentDraft,
    DocumentReviewItem,
    HabitatIdentity,
    KnowledgeDocument,
    PlantIdentity,
)


from src.storage.identity_resolution import AdministrativeRegistry


def _make_draft_with_reviews(reviews: list[DocumentReviewItem]) -> DocumentDraft:
    plant = PlantIdentity(id="plant_ui", label="Cabai Rawit", identity_level="cultivar")
    ar = AdministrativeRegistry()
    habitat = ar.lookup("Daerah Istimewa Yogyakarta", "Kabupaten Sleman", "Kecamatan Pakem", "Desa Hargobinangun")
    doc_key = f"{plant.id}:{habitat.id}"
    doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[],
        attributes={},
        media_refs=[],
        updated_by_run="run_ui_v2",
        doc_id=doc_key,
    )
    for r in reviews:
        r.target_document_key = doc_key
    return DocumentDraft(
        run_id="run_ui_v2",
        source_filename="input.xlsx",
        file_sha256="1" * 64,
        source_uri="cas:///sources/input.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc},
        reviews=reviews,
        base_versions={doc_key: 0},
    )


def test_u01_no_hardcoded_reason_and_short_reason_blocks_action():
    """U-01: No hardcoded reason in payload; empty or short reason (<10 chars) blocks apply/revise calls."""
    rev_ow = DocumentReviewItem(
        item_id="rev_ow_u01",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 90.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": 90.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    draft = _make_draft_with_reviews([rev_ow])

    # Simulate text_input returning empty string
    mock_resolve = MagicMock()
    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.warning") as mock_warning, \
         patch("streamlit.text_input", return_value="short"), \
         patch("streamlit.button", return_value=True), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.streamlit_commit.resolve_review_item_v2", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_v2")

        # Because reason length ("short" = 5 chars) is < 10, no resolve call should be made
        assert not mock_resolve.called
        # A warning or validation message should be surfaced
        assert mock_warning.called


def test_u02_revise_sends_user_input_values_and_reason():
    """U-02: 'Koreksi' sends corrected_value, corrected_unit, and reason from user input."""
    rev_ow = DocumentReviewItem(
        item_id="rev_ow_u02",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="row 2",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "cm",
        },
    )
    draft = _make_draft_with_reviews([rev_ow])

    def mock_text_input(label, key=None, **kwargs):
        if "alasan" in label.lower():
            return "Alasan kurasi valid lebih dari sepuluh karakter"
        if "nilai" in label.lower():
            return "87.5"
        if "satuan" in label.lower():
            return "cm"
        return ""

    def mock_button(label, key=None, **kwargs):
        # Click only 'Koreksi' button
        return "btn_revise" in (key or "") or "koreksi" in label.lower()

    mock_resolve = MagicMock()
    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.rerun"), \
         patch("streamlit.text_input", side_effect=mock_text_input), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock(button=mock_button) for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.streamlit_commit.resolve_review_item_v2", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_v2")

        assert mock_resolve.called
        decision = mock_resolve.call_args.kwargs.get("decision") or mock_resolve.call_args[0][2]
        assert decision["action"] == "REVISE"
        assert decision["reason"] == "Alasan kurasi valid lebih dari sepuluh karakter"
        assert decision["corrected_value"] in (87.5, "87.5")
        assert decision["corrected_unit"] == "cm"
        # Must not contain hardcoded string "Curator correction"
        assert decision["reason"] != "Curator correction"


def test_u03_unit_mismatch_does_not_have_apply_incoming_button():
    """U-03: UNIT_MISMATCH renders only 'Pertahankan Lama' and 'Koreksi' (no 'Terapkan Baru')."""
    rev_unit = DocumentReviewItem(
        item_id="rev_unit_u03",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="row 3",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "UNIT_INCOMPATIBLE",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "kg",
        },
    )
    draft = _make_draft_with_reviews([rev_unit])

    buttons_created: list[str] = []

    def mock_button(label, key=None, **kwargs):
        buttons_created.append(label)
        return False

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.text_input", return_value=""), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock(button=mock_button) for _ in range(spec if isinstance(spec, int) else len(spec))]):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_v2")

    # In UNIT_MISMATCH, "Terapkan Baru" must not exist
    labels_lower = [b.lower() for b in buttons_created]
    assert not any("terapkan" in l for l in labels_lower), f"Found forbidden 'Terapkan' in {buttons_created}"
    assert any("pertahankan" in l for l in labels_lower)
    assert any("koreksi" in l for l in labels_lower)


def test_u04_scenario_85kg_vs_80cm_cannot_send_85cm_without_confirmation():
    """U-04: Scenario '85 kg vs 80 cm': without explicit unit confirmation from user, cannot send '85 cm'."""
    rev_unit = DocumentReviewItem(
        item_id="rev_unit_u04",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="row 3",
        raw_values=[80.0, 85.0],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "UNIT_INCOMPATIBLE",
            "old_value": 80.0,
            "new_value": 85.0,
            "old_unit": "cm",
            "new_unit": "kg",
        },
    )
    draft = _make_draft_with_reviews([rev_unit])

    # User inputs corrected_unit as empty string or does not change/confirm
    def mock_text_input(label, key=None, **kwargs):
        if "alasan" in label.lower():
            return "Alasan perbaikan unit mismatch valid"
        if "nilai" in label.lower():
            return "85.0"
        if "satuan" in label.lower():
            return ""  # Empty unit input
        return ""

    def mock_button(label, key=None, **kwargs):
        return "koreksi" in label.lower() or "btn_revise" in (key or "")

    mock_resolve = MagicMock()
    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.warning"), \
         patch("streamlit.text_input", side_effect=mock_text_input), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock(button=mock_button) for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.streamlit_commit.resolve_review_item_v2", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_v2")

        # Because corrected_unit is empty, it must not blindly call resolve with "cm"
        if mock_resolve.called:
            call_dict = mock_resolve.call_args.kwargs.get("decision") or mock_resolve.call_args[0][2]
            assert call_dict.get("corrected_unit") != "cm"


def test_u05_other_categories_remain_unchanged():
    """U-05: Other categories (e.g. NEW_ATTRIBUTE) retain default 2-button (Approve/Reject) controls."""
    rev_other = DocumentReviewItem(
        item_id="rev_other_u05",
        category="NEW_ATTRIBUTE",
        source_label="aroma buah",
        source_context="row 5",
        raw_values=["harum"],
        status="pending",
        payload={"attribute_id": "attr_aroma_buah"},
    )
    draft = _make_draft_with_reviews([rev_other])

    buttons_created: list[str] = []

    def mock_button(label, key=None, **kwargs):
        buttons_created.append(label)
        return False

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock(button=mock_button) for _ in range(spec if isinstance(spec, int) else len(spec))]):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_v2")

    labels_lower = [b.lower() for b in buttons_created]
    assert any("setujui" in l for l in labels_lower)
    assert any("tolak" in l for l in labels_lower)
