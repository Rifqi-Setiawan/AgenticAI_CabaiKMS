from src.agents.schema_matching.anchor import AnchorResult
from src.agents.schema_matching.source_parsing import ParsedAttribute
from src.ingestion.shadow_parity import compare_shadow_parity
from src.schema.source_ir import SourceIR


def _anchor(candidates, **kwargs):
    selected = next((item.column_name for item in candidates if item.column_name == "Variety"), None)
    return AnchorResult("found" if selected else "escalate", selected, 1.0, "test")


def _ir(attributes, *, orientation="row-oriented", entities=None):
    observation_positions = (
        [{"position_index": index, "row": index + 2} for index in range(3)]
        if orientation == "row-oriented"
        else [
            {
                "position_index": index,
                "column_letter": chr(ord("B") + index),
                "header_coordinate": f"{chr(ord('B') + index)}1",
                "raw_entity_label": value,
            }
            for index, value in enumerate(entities or [])
        ]
    )
    source_attributes = []
    for attribute_index, (label, context, values) in enumerate(attributes):
        source_attributes.append({
            "source_attribute_id": f"Sheet!COL:{attribute_index}",
            "axis": "column" if orientation == "row-oriented" else "row",
            "axis_coordinate": str(attribute_index),
            "raw_label": label,
            "header_path": ([context] if context else []) + [label],
            "header_cells": [f"A{attribute_index + 1}"],
            "structural_context": context,
            "detected_value_type": "mixed",
            "values": [
                {
                    "position_index": index,
                    "coordinate": f"B{index + 2}",
                    "raw_value": value,
                    "value_type": "empty" if value is None else "string",
                }
                for index, value in enumerate(values)
            ],
        })
    return SourceIR(
        source_file_name="fixture.xlsx",
        source_file_sha256="abc",
        sheet_name="Sheet",
        tables=[{
            "table_index": 0,
            "sheet_name": "Sheet",
            "table_range": "A1:D4",
            "orientation": orientation,
            "observation_positions": observation_positions,
            "attributes": source_attributes,
            "structure_confidence": 0.1,
        }],
    )


def _legacy(attributes):
    return [ParsedAttribute(label, context, values) for label, context, values in attributes]


def test_simple_row_oriented_exact_parity_matches_independent_of_confidence():
    attributes = [("Variety", None, ["Domba", "Gendot", None]), ("Height", None, ["10", None, "12"])]
    report = compare_shadow_parity(
        _legacy(attributes), _ir(attributes), source_format="row-oriented", anchor_detector=_anchor
    )
    assert report.status.value == "MATCH"
    assert report.attribute_identity_parity == 1.0
    assert report.value_position_parity == 1.0
    assert report.anchor_match and report.anchor_values_match


def test_positional_blank_divergence_reports_indices():
    legacy = [("Variety", None, ["Domba", "Gendot", "Kopay"]), ("Height", None, ["10", None, "12"])]
    new = [("Variety", None, ["Domba", "Gendot", "Kopay"]), ("Height", None, ["10", "12", None])]
    report = compare_shadow_parity(
        _legacy(legacy), _ir(new), source_format="row-oriented", anchor_detector=_anchor
    )
    assert report.status.value == "DIFFERENT"
    height = next(item for item in report.attributes if item.legacy_identity == "Height")
    assert [item.position_index for item in height.position_mismatches] == [1, 2]


def test_context_difference_is_missing_and_extra_full_identity():
    legacy = [("Length", "Young Fruit", ["3"])]
    new = [("Length", "Mature Fruit", ["3"])]
    report = compare_shadow_parity(
        _legacy(legacy), _ir(new), source_format="row-oriented", anchor_detector=_anchor
    )
    assert report.status.value == "DIFFERENT"
    assert report.legacy_only_attributes == ["Young Fruit / Length"]
    assert report.source_ir_only_attributes == ["Mature Fruit / Length"]


def test_missing_and_extra_attributes_are_explicit():
    legacy = [("A", None, ["1"]), ("B", None, ["2"]), ("C", None, ["3"])]
    missing = compare_shadow_parity(
        _legacy(legacy), _ir([legacy[0], legacy[2]]),
        source_format="row-oriented", anchor_detector=_anchor,
    )
    assert missing.legacy_only_attributes == ["B"]
    extra = compare_shadow_parity(
        _legacy([legacy[0], legacy[2]]), _ir(legacy),
        source_format="row-oriented", anchor_detector=_anchor,
    )
    assert extra.source_ir_only_attributes == ["B"]


def test_orientation_disagreement_is_explicit():
    attributes = [("A", None, ["1"])]
    report = compare_shadow_parity(
        _legacy(attributes), _ir(attributes, orientation="transposed", entities=["Domba"]),
        source_format="row-oriented", anchor_detector=_anchor,
    )
    assert report.status.value == "DIFFERENT"
    assert "ORIENTATION_MISMATCH" in report.issue_codes


def test_transposed_entity_positions_match_exactly():
    attributes = [("Habit", None, ["terna", None, "perdu"])]
    report = compare_shadow_parity(
        _legacy(attributes),
        _ir(attributes, orientation="transposed", entities=["Domba", "Gendot", "Kopay"]),
        source_format="transposed",
        legacy_entity_names=["Domba", "Gendot", "Kopay"],
    )
    assert report.status.value == "MATCH"
    assert report.entity_names_match


def test_repeated_leaves_under_distinct_contexts_match():
    attributes = [
        ("Variety", None, ["Domba"]),
        ("Length", "Young Fruit", ["3"]),
        ("Length", "Mature Fruit", ["5"]),
    ]
    report = compare_shadow_parity(
        _legacy(attributes), _ir(attributes), source_format="row-oriented", anchor_detector=_anchor
    )
    assert report.status.value == "MATCH"
    assert report.matched_attribute_count == 3


def test_attribute_order_difference_is_reported_without_guessing():
    legacy = [("Variety", None, ["Domba"]), ("A", None, ["1"]), ("B", None, ["2"])]
    new = [legacy[0], legacy[2], legacy[1]]
    report = compare_shadow_parity(
        _legacy(legacy), _ir(new), source_format="row-oriented", anchor_detector=_anchor
    )
    assert report.status.value == "DIFFERENT"
    assert not report.order_match
    assert "ATTRIBUTE_ORDER_MISMATCH" in report.issue_codes
