"""Tests for Round 5: Separate Hint vs Exact Match in Signal Fusion (G-4)."""

from __future__ import annotations

import pytest

from src.agents.signal_fusion import FusionAction, fuse_photo_signals
from src.agents.variety_registry import VarietyEntry, VarietyRegistry
from src.agents.vision_classification import extract_photo_context_signal


def test_s1_other_with_subset_filename_produces_candidate_with_suggestion():
    """S1: OTHER high confidence + filename 'rawit_merah.jpg' (registry: Rawit, Rawit Hijau) -> CANDIDATE with suggested name."""
    reg = VarietyRegistry.build(
        spreadsheet_varieties=["Cabai Rawit", "Cabai Rawit Hijau"]
    )

    # Context signal from filename "rawit_merah_001.jpg"
    signal = extract_photo_context_signal("rawit_merah_001.jpg", registry=reg)
    # The hint may suggest "Cabai Rawit", but because it's a token subset (not exact "rawit merah"), is_exact_hint must be False!
    assert signal.is_exact_hint is False

    vis_res = {
        "classification_status": "OTHER",
        "visual_confidence": 0.92,
        "matched_variety": None,
        "identified_part": "buah",
        "visual_evidence": "Buah merah tegak lancip",
    }

    # Fusion must recognize this as a new candidate variety, NOT a conflict!
    outcome = fuse_photo_signals(
        filename_match=signal.suggested_variety_hint,
        registry_known=reg,
        visual_result=vis_res,
        is_exact_hint=signal.is_exact_hint,
        raw_filename="rawit_merah_001.jpg",
    )
    assert outcome.action == FusionAction.CANDIDATE
    assert "rawit_merah" in (outcome.suggested_candidate_name or "").lower() or "rawit merah" in (outcome.suggested_candidate_name or "").lower()


def test_s2_other_with_exact_filename_produces_review_mismatch():
    """S2: OTHER high confidence + filename exactly 'rawit_hijau.jpg' -> REVIEW_MISMATCH (real contradiction)."""
    reg = VarietyRegistry.build(
        spreadsheet_varieties=["Cabai Rawit", "Cabai Rawit Hijau"]
    )

    signal = extract_photo_context_signal("rawit_hijau.jpg", registry=reg)
    assert signal.is_exact_hint is True
    assert signal.suggested_variety_hint == "Cabai Rawit Hijau"

    vis_res = {
        "classification_status": "OTHER",
        "visual_confidence": 0.90,
        "matched_variety": None,
        "identified_part": "buah",
        "visual_evidence": "Daun bulat buah oranye",
    }

    # Filename explicitly claims known variety "Cabai Rawit Hijau", but VLM says OTHER -> REVIEW_MISMATCH
    outcome = fuse_photo_signals(
        filename_match=signal.suggested_variety_hint,
        registry_known=reg,
        visual_result=vis_res,
        is_exact_hint=signal.is_exact_hint,
    )
    assert outcome.action == FusionAction.REVIEW_MISMATCH
    assert outcome.signals_consistent is False


def test_s3_prefix_cabai_cabe_normalized_exact_match():
    """S3: KNOWN + 'Cabai Rawit' vs canonical 'Rawit': prefix normalization 'cabai/cabe' is exact match."""
    reg = VarietyRegistry.build(
        spreadsheet_varieties=["Rawit"]
    )

    signal = extract_photo_context_signal("cabai_rawit.jpg", registry=reg)
    assert signal.is_exact_hint is True
    assert signal.suggested_variety_hint == "Rawit"

    vis_res = {
        "classification_status": "KNOWN",
        "visual_confidence": 0.95,
        "matched_variety": "Rawit",
        "identified_part": "buah",
        "visual_evidence": "Buah rawit",
    }

    outcome = fuse_photo_signals(
        filename_match=signal.suggested_variety_hint,
        registry_known=reg,
        visual_result=vis_res,
        is_exact_hint=signal.is_exact_hint,
    )
    assert outcome.action == FusionAction.AUTO_LINK
    assert outcome.matched_variety == "Rawit"
    assert outcome.signals_consistent is True
