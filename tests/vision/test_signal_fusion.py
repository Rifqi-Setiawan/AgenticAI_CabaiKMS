"""Unit tests for B-2: Three-Way Signal Fusion Logic (F1..F8).

Tests:
F1: AUTO_LINK: status KNOWN, visual >= threshold, in registry, filename matches or neutral.
F2: REVIEW_MISMATCH: Filename misleading ("cabai_rawit.jpg" but visual shows Keriting).
F3: REVIEW_MISMATCH: status KNOWN, but matched variety is outside registry.
F4: CANDIDATE: status OTHER, visual >= other_threshold (>=0.80), no registry match in filename.
F5: REVIEW_MISMATCH: status OTHER >= 0.80, but filename claims a known registered variety.
F6: REVIEW_UNCERTAIN: status UNCERTAIN (never promoted to CANDIDATE).
F7: REVIEW_UNCERTAIN: status KNOWN, but visual confidence below threshold (<0.85).
F8: REVIEW_UNCERTAIN: status OTHER, but visual confidence below threshold (<0.80).
"""

from __future__ import annotations

import pytest

from src.agents.signal_fusion import (
    FusionAction,
    FusionOutcome,
    FusionThresholds,
    fuse_photo_signals,
)
from src.schema.contracts import VisionClassificationResult


@pytest.fixture
def registry_known():
    return ["Cabai Rawit", "Cabai Keriting", "Cabai Habanero"]


def test_f1_auto_link_consistent_known(registry_known):
    """F1: AUTO_LINK on high-confidence KNOWN consistent with registry and filename."""
    vis = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Rawit",
        confidence=0.92,
        identified_part="buah",
        visual_evidence="Buah tegak merah kecil",
    )
    outcome = fuse_photo_signals(
        filename_match="Cabai Rawit",
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.AUTO_LINK
    assert outcome.matched_variety == "Cabai Rawit"
    assert outcome.confidence == 0.92
    assert outcome.signals_consistent is True


def test_f2_review_mismatch_adversarial_filename(registry_known):
    """F2: REVIEW_MISMATCH when filename claims Rawit but image shows Keriting (visual wins, conflict -> review)."""
    vis = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Keriting",
        confidence=0.90,
        identified_part="buah",
        visual_evidence="Buah bergelombang panjang ramping",
    )
    outcome = fuse_photo_signals(
        filename_match="Cabai Rawit",
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_MISMATCH
    assert outcome.signals_consistent is False
    assert "contradicts" in outcome.reason.lower()


def test_f3_review_mismatch_variety_outside_registry(registry_known):
    """F3: REVIEW_MISMATCH when visual matched variety is not present in registry."""
    vis = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Jalapeno",  # not in registry_known
        confidence=0.88,
        identified_part="buah",
        visual_evidence="Buah bulat tumpul tebal",
    )
    outcome = fuse_photo_signals(
        filename_match=None,
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_MISMATCH
    assert "not in registry" in outcome.reason.lower()


def test_f4_candidate_on_high_confidence_other(registry_known):
    """F4: CANDIDATE when visual status is OTHER with confidence >= 0.80 and no registry filename clash."""
    vis = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        confidence=0.85,
        identified_part="buah",
        visual_evidence="Karakteristik buah unik tidak cocok dengan varietas terdaftar",
    )
    outcome = fuse_photo_signals(
        filename_match=None,
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.CANDIDATE
    assert outcome.confidence == 0.85
    assert outcome.matched_variety is None


def test_f5_review_mismatch_other_conflicts_with_registered_filename(registry_known):
    """F5: REVIEW_MISMATCH when visual is OTHER but filename claims a known registered variety."""
    vis = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        confidence=0.85,
        identified_part="buah",
        visual_evidence="Morfologi varietas baru",
    )
    outcome = fuse_photo_signals(
        filename_match="Cabai Rawit",  # known in registry
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_MISMATCH
    assert outcome.signals_consistent is False


def test_f6_review_uncertain_status(registry_known):
    """F6: REVIEW_UNCERTAIN when status is UNCERTAIN (never promoted to CANDIDATE)."""
    vis = VisionClassificationResult(
        classification_status="UNCERTAIN",
        matched_variety=None,
        confidence=0.60,
        identified_part="daun",
        visual_evidence="Citra buram",
    )
    outcome = fuse_photo_signals(
        filename_match=None,
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_UNCERTAIN
    assert outcome.action != FusionAction.CANDIDATE


def test_f7_review_uncertain_known_low_confidence(registry_known):
    """F7: REVIEW_UNCERTAIN when status is KNOWN but confidence < 0.85 threshold."""
    vis = VisionClassificationResult(
        classification_status="KNOWN",
        matched_variety="Cabai Rawit",
        confidence=0.84,  # below 0.85
        identified_part="buah",
        visual_evidence="Mirip rawit tapi keyakinan rendah",
    )
    outcome = fuse_photo_signals(
        filename_match="Cabai Rawit",
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_UNCERTAIN


def test_f8_review_uncertain_other_low_confidence(registry_known):
    """F8: REVIEW_UNCERTAIN when status is OTHER but confidence < 0.80 threshold."""
    vis = VisionClassificationResult(
        classification_status="OTHER",
        matched_variety=None,
        confidence=0.79,  # below 0.80
        identified_part="buah",
        visual_evidence="Kemungkinan varietas lain tapi ragu",
    )
    outcome = fuse_photo_signals(
        filename_match=None,
        registry_known=registry_known,
        visual_result=vis,
    )
    assert outcome.action == FusionAction.REVIEW_UNCERTAIN
    assert outcome.action != FusionAction.CANDIDATE
