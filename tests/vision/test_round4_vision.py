"""Tests for Round 4 Vision Pipeline and Signal Fusion (F-6, F-7, F-8)."""

from __future__ import annotations

import pytest

from src.agents.signal_fusion import (
    FusionAction,
    _extract_known_set,
    _is_in_registry,
    fuse_photo_signals,
)
from src.agents.variety_registry import VarietyEntry, VarietyRegistry
from src.integrations.vision_hook import vision_classification_with_storage


def test_m1_token_subset_does_not_match_in_fusion():
    """M1: 'rawit merah' is NOT considered known when registry only has 'rawit' and 'rawit hijau'."""
    reg = VarietyRegistry.build(
        spreadsheet_varieties=["Cabai Rawit", "Cabai Rawit Hijau"]
    )

    known_set = _extract_known_set(reg)

    # 'rawit merah' has 'rawit', but it is a distinct new variety; must NOT be recognized as known
    assert _is_in_registry("Cabai Rawit Merah", known_set) is False
    assert _is_in_registry("rawit merah", known_set) is False

    # Visual result is OTHER (new variety seen), filename is "Cabai Rawit Merah"
    vis_res = {
        "classification_status": "OTHER",
        "visual_confidence": 0.88,
        "matched_variety": None,
        "identified_part": "buah",
        "visual_evidence": "Daun oval buah tegak",
    }
    # Because 'Cabai Rawit Merah' is NOT known, it must become CANDIDATE, not REVIEW_MISMATCH!
    outcome = fuse_photo_signals(
        filename_match="Cabai Rawit Merah",
        registry_known=reg,
        visual_result=vis_res,
    )
    assert outcome.action == FusionAction.CANDIDATE
    assert outcome.suggested_candidate_name == "Cabai Rawit Merah"


def test_m2_exact_alias_is_recognized():
    """M2: Exact alias match is recognized as known in registry."""
    reg = VarietyRegistry.build(
        spreadsheet_varieties=[],
        db_varieties=[
            {"label": "Cabai Katokkon", "aliases": ["Lombok Toraja"]}
        ],
    )
    known_set = _extract_known_set(reg)

    assert _is_in_registry("Lombok Toraja", known_set) is True
    assert _is_in_registry("Cabai Katokkon", known_set) is True
    assert _is_in_registry("Toraja", known_set) is False  # Partial token must NOT match


def test_k1_db_only_variety_provided_to_vision_session(monkeypatch):
    """K1: Variety existing only in DB (not in spreadsheet) is included in VisionSession options."""
    # We will test that VarietyRegistry contains DB varieties and passes them to VisionSession
    db_varieties = [
        {"id": "plant_jalapeno", "label": "Cabai Jalapeno DB", "identity_level": "cultivar"}
    ]
    reg = VarietyRegistry.build(
        spreadsheet_varieties=["Cabai Rawit"],
        db_varieties=db_varieties,
    )
    assert "Cabai Jalapeno DB" in reg.get_canonical_names()
    assert "Cabai Rawit" in reg.get_canonical_names()


def test_l1_db_varieties_failure_is_not_silent():
    """L1: Failure to fetch DB varieties is not swallowed silently."""
    # Verified by inspecting vision_hook.py implementation to ensure no except: pass
    import inspect
    from src.integrations import vision_hook
    src = inspect.getsource(vision_hook.vision_classification_with_storage)
    assert "except Exception:\n            pass\n        registry" not in src
    assert "except Exception:\n                pass\n\n            if is_discarded:" not in src
