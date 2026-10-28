"""Unit tests for B-1: Dynamic Variety Registry and Context Signal Extraction (R1..R6).

Tests:
R1: VarietyRegistry.build creates union of spreadsheet varieties and database varieties.
R2: Alias matching: registered alias resolves to the canonical variety.
R3: Variety absent from manual hardcoded list is successfully detected via registry.
R4: Unknown variety text yields no match.
R5: Matching is strictly deterministic across repeated calls.
R6: extract_photo_context_signal without registry preserves legacy behavior, while
    providing a registry uses registry signals without hardcoded fallback.
"""

from __future__ import annotations

import pytest

from src.agents.variety_registry import VarietyEntry, VarietyMatchResult, VarietyRegistry
from src.agents.vision_classification import extract_photo_context_signal


def test_r1_union_spreadsheet_and_db_varieties():
    """R1: VarietyRegistry.build merges spreadsheet and DB varieties into a single registry."""
    spreadsheet_vars = ["Cabai Rawit", "Cabai Keriting"]
    db_vars = [
        {"id": "plant_hiyung", "label": "Cabai Hiyung", "aliases": ["hiyung", "cabe hiyung"]},
        {"id": "plant_rawit", "label": "Cabai Rawit", "aliases": ["rawit domba"]},
    ]

    registry = VarietyRegistry.build(spreadsheet_vars, db_vars)
    names = registry.get_canonical_names()

    assert "Cabai Rawit" in names
    assert "Cabai Keriting" in names
    assert "Cabai Hiyung" in names
    assert len(names) == 3

    # Cabai Rawit is present in both
    rawit_entry = registry.get_entry("Cabai Rawit")
    assert rawit_entry is not None
    assert rawit_entry.source == "both"
    assert "rawit domba" in rawit_entry.aliases


def test_r2_alias_matching():
    """R2: Registered aliases resolve to the correct canonical name."""
    db_vars = [
        {"id": "plant_keriting", "label": "Cabai Keriting", "aliases": ["lado", "lado kriting"]},
    ]
    registry = VarietyRegistry.build([], db_vars)

    matches = registry.match("foto_tanaman_lado_daun.jpg")
    assert len(matches) > 0
    top = matches[0]
    assert top.canonical_name == "Cabai Keriting"
    assert "alias" in top.reason.lower()


def test_r3_non_manual_variety_detected_via_registry():
    """R3: A variety not present in the old hardcoded list is detected via registry."""
    # 'Ceta Kudeti' or 'Hiyung' was never in the hardcoded list
    registry = VarietyRegistry.build(["Cabai Ceta Kudeti"])

    matches = registry.match("DSC_0012_ceta_kudeti_buah.png")
    assert len(matches) > 0
    assert matches[0].canonical_name == "Cabai Ceta Kudeti"


def test_r4_unknown_variety_returns_empty():
    """R4: Text without any known variety yields no match."""
    registry = VarietyRegistry.build(["Cabai Rawit", "Cabai Keriting"])

    matches = registry.match("foto_hama_belalang_daun.png")
    assert len(matches) == 0


def test_r5_matching_is_deterministic():
    """R5: Match results are strictly deterministic in order and scores."""
    registry = VarietyRegistry.build(
        ["Cabai Rawit Merah", "Cabai Rawit Hijau", "Cabai Keriting"],
        [{"id": "plant_rawit", "label": "Cabai Rawit", "aliases": ["rawit"]}],
    )
    query = "rawit_daun_01.jpg"

    res1 = registry.match(query)
    res2 = registry.match(query)
    res3 = registry.match(query)

    assert [(r.canonical_name, r.score, r.reason) for r in res1] == [
        (r.canonical_name, r.score, r.reason) for r in res2
    ] == [(r.canonical_name, r.score, r.reason) for r in res3]


def test_r6_legacy_context_signal_behavior_preserved():
    """R6: extract_photo_context_signal preserves legacy behavior without registry, uses registry when supplied."""
    # Without registry: falls back to hardcoded list if word is in hardcoded list ('rawit' -> 'Cabai Rawit')
    signal_legacy = extract_photo_context_signal("foto_rawit_daun.jpg")
    assert signal_legacy.suggested_variety_hint == "Cabai Rawit"

    # Without registry and without hardcoded match: returns None
    signal_legacy_unknown = extract_photo_context_signal("foto_hiyung_daun.jpg")
    assert signal_legacy_unknown.suggested_variety_hint is None

    # With registry: detects custom variety not in hardcoded list
    custom_registry = VarietyRegistry.build(["Cabai Hiyung"])
    signal_custom = extract_photo_context_signal("foto_hiyung_daun.jpg", registry=custom_registry)
    assert signal_custom.suggested_variety_hint == "Cabai Hiyung"
