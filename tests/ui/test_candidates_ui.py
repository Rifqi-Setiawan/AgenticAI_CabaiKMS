"""Unit tests for B-4: Streamlit UI Candidate Review and Habitat Unknown Panels.

Tests:
1. Reason input is required and minimum 10 characters before triggering resolve.
2. No hardcoded reason strings; payload reflects exact user input.
3. PROMOTE without habitat leaves habitat field empty/None (no invented values).
4. Candidates are rendered individually (no grouping/clustering).
5. Documents needing habitat panel renders and allows habitat assignment.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from src.integrations.candidates_ui import (
    render_candidates_panel,
    render_habitat_unknown_documents_panel,
)


def _make_sample_candidate(cid: str = "cand_01", fname: str = "cabe_01.png") -> dict:
    return {
        "candidate_id": cid,
        "asset_id": "a" * 64,
        "run_id": "run_01",
        "source_filename": fname,
        "original_sha256": "1" * 64,
        "organ_part": "buah",
        "suggested_name": "Cabai Unik",
        "visual_evidence": {"color": "orange", "shape": "conical"},
        "confidence": 0.88,
        "status": "CANDIDATE",
        "media_url": f"/media/{'a'*64}",
    }


def test_ui_candidate_empty_or_short_reason_blocks_action():
    """Empty or short reason (<10 characters) shows warning and prevents API call."""
    cand = _make_sample_candidate()
    mock_resolve = MagicMock()

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.image"), \
         patch("streamlit.warning") as mock_warning, \
         patch("streamlit.text_input", return_value="pendek"), \
         patch("streamlit.button", return_value=True), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.candidates_ui.resolve_candidate_api", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        render_candidates_panel([cand])
        assert not mock_resolve.called


def test_ui_candidate_promote_sends_user_reason_and_name():
    """PROMOTE action sends exact user-supplied reason and variety name without hardcoding."""
    cand = _make_sample_candidate()
    mock_resolve = MagicMock()

    # User enters valid name and reason
    def _fake_text_input(label, value="", key=None, **kwargs):
        if "alasan" in label.lower():
            return "Varietas baru ditemukan di lereng gunung Merapi"
        if "nama varietas" in label.lower():
            return "Cabai Merapi Super"
        return value

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.image"), \
         patch("streamlit.warning"), \
         patch("streamlit.text_input", side_effect=_fake_text_input), \
         patch("streamlit.button", side_effect=lambda label, key=None, **kw: "promote" in (key or "").lower()), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.candidates_ui.resolve_candidate_api", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        render_candidates_panel([cand])
        assert mock_resolve.called
        decision = mock_resolve.call_args[0][1]
        assert decision["action"] == "PROMOTE"
        assert decision["new_variety_name"] == "Cabai Merapi Super"
        assert decision["reason"] == "Varietas baru ditemukan di lereng gunung Merapi"


def test_ui_promote_without_habitat_leaves_habitat_none():
    """PROMOTE without habitat leaves habitat field None (sentinel habitat handled by server)."""
    cand = _make_sample_candidate()
    mock_resolve = MagicMock()

    def _fake_text_input(label, value="", key=None, **kwargs):
        if "alasan" in label.lower():
            return "Varietas tanpa lokasi administratif definitif"
        if "nama varietas" in label.lower():
            return "Cabai Unknown Loc"
        if "habitat" in label.lower():
            return ""  # Empty
        return value

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.image"), \
         patch("streamlit.warning"), \
         patch("streamlit.text_input", side_effect=_fake_text_input), \
         patch("streamlit.button", side_effect=lambda label, key=None, **kw: "promote" in (key or "").lower()), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]), \
         patch("src.integrations.candidates_ui.resolve_candidate_api", mock_resolve):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        render_candidates_panel([cand])
        assert mock_resolve.called
        decision = mock_resolve.call_args[0][1]
        assert decision.get("habitat") is None
        assert decision.get("habitat_id") is None


def test_ui_candidates_rendered_individually():
    """Candidates are rendered individually without clustering."""
    cand1 = _make_sample_candidate("c1", "img1.png")
    cand2 = _make_sample_candidate("c2", "img2.png")

    rendered_keys = []
    def _capture_button(label, key=None, **kw):
        if key:
            rendered_keys.append(key)
        return False

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.image"), \
         patch("streamlit.warning"), \
         patch("streamlit.text_input", return_value="alasan panjang valid"), \
         patch("streamlit.button", side_effect=_capture_button), \
         patch("streamlit.columns", side_effect=lambda spec: [MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))]):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        render_candidates_panel([cand1, cand2])
        assert any("c1" in k for k in rendered_keys)
        assert any("c2" in k for k in rendered_keys)


def test_ui_habitat_unknown_documents_panel():
    """Habitat unknown documents panel lists documents and allows habitat assignment."""
    docs = [
        {
            "id": "plant_unknown:habitat_unknown",
            "variety": {"label": "Cabai Unik Tanpa Habitat"},
            "habitat_unknown": True,
            "media_refs": [{"asset_id": "a" * 64}],
        }
    ]
    mock_set_hab = MagicMock()

    with patch("streamlit.expander") as mock_expander, \
         patch("streamlit.write"), \
         patch("streamlit.subheader"), \
         patch("streamlit.text_input", return_value="Desa Sukamaju"), \
         patch("streamlit.button", return_value=True), \
         patch("src.integrations.candidates_ui.set_document_habitat_api", mock_set_hab):
        mock_expander.return_value.__enter__.return_value = MagicMock()
        mock_expander.return_value.__exit__.return_value = False

        render_habitat_unknown_documents_panel(docs)
        assert mock_set_hab.called
