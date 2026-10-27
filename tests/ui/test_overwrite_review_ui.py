"""UI tests for L3: Review queue rendering for OVERWRITE_BLOCKED and UNIT_MISMATCH (T-22, T-23).

Tests:
T-22: UI renders OVERWRITE_BLOCKED and UNIT_MISMATCH displaying old vs new value,
      units, reason code, and 3 actions (KEEP_EXISTING, APPLY_INCOMING, REVISE).
T-23: Other review categories remain unchanged (generic approve/reject controls).
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


def _make_draft_with_reviews(reviews: list[DocumentReviewItem]) -> DocumentDraft:
    plant = PlantIdentity(id="plant_test", label="Cabai Test", identity_level="cultivar")
    habitat = HabitatIdentity(
        id="hab_test",
        label="Desa Test",
        administrative_path={
            "province_name": "DIY",
            "regency_name": "Sleman",
            "district_name": "Pakem",
            "village_name": "Test",
        },
    )
    doc_key = f"{plant.id}:{habitat.id}"
    doc = KnowledgeDocument(
        schema_version="kms-document-v1",
        variety=plant,
        habitat=habitat,
        sampling_locations=[],
        attributes={},
        media_refs=[],
        updated_by_run="run_ui_test",
    )
    return DocumentDraft(
        run_id="run_ui_test",
        source_filename="test.xlsx",
        file_sha256="a" * 64,
        source_uri="cas:///sources/test.xlsx",
        source_scope="test",
        schema_version="kms-document-v1",
        template_hash="1" * 64,
        config_fingerprint="cfg",
        revision=1,
        documents={doc_key: doc},
        reviews=reviews,
        base_versions={doc_key: 0},
    )


def test_t22_render_overwrite_and_unit_mismatch_categories():
    """T-22: OVERWRITE_BLOCKED and UNIT_MISMATCH display values, units, reason code, and 3 action buttons."""
    rev_ow = DocumentReviewItem(
        item_id="rev_ow_01",
        category="OVERWRITE_BLOCKED",
        source_label="tinggi tanaman",
        source_context="Row 2: overwrite blocked",
        raw_values=[80.0, "sangat tinggi"],
        status="pending",
        payload={
            "attribute_id": "attr_tinggi_tanaman",
            "reason_code": "TYPE_MISMATCH",
            "old_value": 80.0,
            "new_value": "sangat tinggi",
            "old_unit": "cm",
            "new_unit": None,
        },
    )
    rev_unit = DocumentReviewItem(
        item_id="rev_unit_01",
        category="UNIT_MISMATCH",
        source_label="tinggi tanaman",
        source_context="Row 3: unit mismatch",
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

    draft = _make_draft_with_reviews([rev_ow, rev_unit])

    written_texts: list[str] = []
    button_keys: list[str] = []

    def mock_write(*args, **kwargs):
        for a in args:
            written_texts.append(str(a))

    def mock_button(label, key=None, **kwargs):
        if key:
            button_keys.append(str(key))
        return False

    def mock_columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            m = MagicMock()
            m.button.side_effect = mock_button
            cols.append(m)
        return cols

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write", side_effect=mock_write), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=mock_columns):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_test")

    full_text = " ".join(written_texts)
    # Check old vs new values displayed
    assert "80.0" in full_text or "80" in full_text
    assert "sangat tinggi" in full_text
    # Check reason codes displayed
    assert "TYPE_MISMATCH" in full_text
    assert "UNIT_INCOMPATIBLE" in full_text

    # Check 3 actions rendered per item: keep (KEEP_EXISTING), apply (APPLY_INCOMING), revise (REVISE)
    assert any("keep" in k for k in button_keys), f"Expected 'keep' action button in {button_keys}"
    assert any("apply" in k for k in button_keys), f"Expected 'apply' action button in {button_keys}"
    assert any("rev" in k for k in button_keys), f"Expected 'revise' action button in {button_keys}"


def test_t23_other_categories_remain_unchanged():
    """T-23: Standard review categories like NEW_ATTRIBUTE retain default 2-button action layout."""
    rev_attr = DocumentReviewItem(
        item_id="rev_attr_01",
        category="NEW_ATTRIBUTE",
        source_label="aroma buah",
        source_context="Row 4: novel attribute",
        raw_values=["harum"],
        status="pending",
    )

    draft = _make_draft_with_reviews([rev_attr])

    button_keys: list[str] = []

    def mock_button(label, key=None, **kwargs):
        if key:
            button_keys.append(str(key))
        return False

    def mock_columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        cols = []
        for _ in range(n):
            m = MagicMock()
            m.button.side_effect = mock_button
            cols.append(m)
        return cols

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.button", side_effect=mock_button), \
         patch("streamlit.columns", side_effect=mock_columns):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        streamlit_commit.render_categorized_review_queue(draft, run_id="run_ui_test")

    # Generic categories render btn_app_ and btn_rej_
    assert "btn_app_rev_attr_01" in button_keys
    assert "btn_rej_rev_attr_01" in button_keys
