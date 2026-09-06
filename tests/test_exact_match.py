from pathlib import Path

import pytest

from src.agents.schema_matching.exact_match import (
    ExactNameStatus,
    mapping_from_exact_resolution,
    resolve_exact_name,
)
from src.schema.canonical import CanonicalRow, CanonicalSchema


def _schema(*rows):
    return CanonicalSchema(
        rows=list(rows),
        template_hash="synthetic",
        template_path=Path("synthetic.xlsx"),
    )


def _row(row_id, key, label, aliases=()):
    return CanonicalRow(row_id, key, label, "test", alt_labels=tuple(aliases))


def test_unique_label_and_case_whitespace_normalization():
    schema = _schema(_row("r_2", "tinggi_tanaman", "Tinggi Tanaman"))
    direct = resolve_exact_name("Tinggi Tanaman", schema)
    formatted = resolve_exact_name("   TINGGI   TANAMAN ", schema)
    assert direct.status is ExactNameStatus.MATCH
    assert formatted.status is ExactNameStatus.MATCH
    assert formatted.canonical_row_id == "r_2"
    assert formatted.canonical_key == "tinggi_tanaman"
    assert formatted.matched_name_type == "label"


def test_unique_curated_alias_maps_and_builds_compatible_mapping():
    schema = _schema(
        _row("r_5", "jumlah_biji", "jumlah biji/buah masak", ["Seeds per mature fruit"])
    )
    resolution = resolve_exact_name("seeds per mature fruit", schema)
    assert resolution.status is ExactNameStatus.MATCH
    assert resolution.matched_name == "Seeds per mature fruit"
    assert resolution.matched_name_type == "alias"
    mapping = mapping_from_exact_resolution(
        resolution,
        source_attribute="seeds per mature fruit",
        source_context="Mature Fruit",
        source_format="row-oriented",
    )
    assert mapping.target_canonical_row == "r_5"
    assert mapping.confidence == 1.0
    assert mapping.normalization_required is True


def test_typo_is_not_fuzzy_matched():
    schema = _schema(_row("r_2", "tinggi_tanaman", "Tinggi Tanaman"))
    assert resolve_exact_name("Tinggi Tanamann", schema).status is ExactNameStatus.NO_MATCH


def test_duplicate_alias_collision_is_ambiguous_in_semantic_order():
    schema = _schema(
        _row("r_1", "zeta_length", "Zeta", ["length"]),
        _row("r_2", "alpha_length", "Alpha", ["Length"]),
    )
    result = resolve_exact_name("LENGTH", schema)
    assert result.status is ExactNameStatus.AMBIGUOUS
    assert result.canonical_row_id is None
    assert result.candidate_canonical_keys == ("alpha_length", "zeta_length")
    assert result.candidate_row_ids == ("r_2", "r_1")


def test_label_alias_collision_is_ambiguous():
    schema = _schema(
        _row("r_1", "length", "Length"),
        _row("r_2", "other_length", "Other", ["Length"]),
    )
    assert resolve_exact_name("Length", schema).status is ExactNameStatus.AMBIGUOUS


def test_duplicate_normalized_name_within_one_row_is_one_match():
    schema = _schema(_row("r_1", "height", "Height", ["HEIGHT", " height "]))
    result = resolve_exact_name("height", schema)
    assert result.status is ExactNameStatus.MATCH
    assert result.candidate_canonical_keys == ("height",)
    assert result.matched_name_type == "label"


def test_mapping_helper_rejects_non_match():
    resolution = resolve_exact_name("missing", _schema(_row("r_1", "height", "Height")))
    with pytest.raises(ValueError, match="unique MATCH"):
        mapping_from_exact_resolution(
            resolution,
            source_attribute="missing",
            source_context=None,
            source_format="row-oriented",
        )
