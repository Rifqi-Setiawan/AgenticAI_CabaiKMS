import openpyxl
import pytest

from src.agents.schema_matching.anchor import AnchorResult
from src.agents.schema_matching.source_parsing import ParsedAttribute
from src.ingestion.runtime_source import (
    RuntimeSourceAttribute,
    RuntimeSourcePreparationError,
    group_attribute_contributions_by_variety,
    physical_source_cells,
    prepare_legacy_runtime_source,
    prepare_source_ir_runtime_source,
    runtime_attribute_from_legacy,
    runtime_attribute_from_source_ir,
)
from src.schema.source_ir import SourceAttributeIR, SourceIR


def _anchor(candidates, **kwargs):
    selected = next((item.column_name for item in candidates if item.column_name == "Variety"), None)
    return AnchorResult("found" if selected else "escalate", selected, 1.0, "test")


def _attribute(label="Height", values=(10, None, 12), *, attribute_id="Sheet!COL:B"):
    return SourceAttributeIR(
        source_attribute_id=attribute_id,
        axis="column",
        axis_coordinate="B",
        raw_label=label,
        header_path=[label],
        header_cells=["B1"],
        detected_value_type="numeric",
        values=[
            {
                "position_index": index,
                "coordinate": f"B{index + 2}",
                "source_coordinate": None if value is None else f"B{index + 2}",
                "raw_value": value,
                "value_type": "empty" if value is None else "integer",
            }
            for index, value in enumerate(values)
        ],
    )


def _source_ir(attributes, *, orientation="row-oriented", entities=None):
    positions = (
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
    return SourceIR(
        source_file_name="fixture.xlsx",
        source_file_sha256="abc",
        sheet_name="Sheet",
        tables=[{
            "table_index": 0,
            "sheet_name": "Sheet",
            "table_range": "A1:D4",
            "orientation": orientation,
            "observation_positions": positions,
            "attributes": attributes,
            "structure_confidence": 0.9,
        }],
    )


def test_legacy_and_source_ir_runtime_adapters_preserve_expected_metadata():
    legacy = runtime_attribute_from_legacy(ParsedAttribute("Height", None, ["10", None]))
    assert legacy.sample_values == ["10"]
    assert legacy.source_attribute_id is None
    assert legacy.logical_value_coordinates == []
    assert legacy.header_path == []
    source = runtime_attribute_from_source_ir(_attribute())
    assert source.row_values == ["10", None, "12"]
    assert source.source_attribute_id == "Sheet!COL:B"
    assert source.logical_value_coordinates == ["B2", "B3", "B4"]
    assert source.physical_value_coordinates == ["B2", None, "B4"]
    assert source.header_path == ["Height"]
    assert source.header_cells == ["B1"]
    assert source.detected_value_type == "numeric"


def test_source_ir_header_path_preserves_order_and_text():
    attribute = _attribute("Length")
    attribute.header_path = ["Morphology", "Mature Fruit", "Length"]
    attribute.header_cells = ["B1", "B2", "B3"]
    runtime = runtime_attribute_from_source_ir(attribute)
    assert runtime.header_path == ["Morphology", "Mature Fruit", "Length"]


def test_source_ir_header_path_cell_alignment_fails_closed():
    attribute = _attribute("Length")
    attribute.header_path = ["Morphology", "Length"]
    attribute.header_cells = ["B1"]
    with pytest.raises(ValueError, match="header_path and header_cells"):
        runtime_attribute_from_source_ir(attribute)


def test_runtime_coordinate_alignment_fails_closed():
    with pytest.raises(ValueError, match="positionally aligned"):
        RuntimeSourceAttribute(
            attribute_name="Height",
            structural_context=None,
            row_values=["10", "12"],
            source_attribute_id="Sheet!COL:B",
            logical_value_coordinates=["B2"],
            physical_value_coordinates=["B2", "B3"],
        )


def test_legacy_preparation_preserves_anchor_positions_and_order(tmp_path):
    path = tmp_path / "legacy.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Data"
    ws.append(["Variety", "Height"])
    ws.append(["Domba", 10])
    ws.append(["Domba", 12])
    ws.append(["Gendot", None])
    wb.save(path)
    wb.close()
    bundle = prepare_legacy_runtime_source(
        path, "Data", source_format="row-oriented", anchor_detector=_anchor
    )
    assert bundle.backend == "legacy"
    assert bundle.anchor_attribute_name == "Variety"
    assert bundle.position_to_variety == ["Domba", "Domba", "Gendot"]
    assert bundle.variety_names == ["Domba", "Gendot"]
    assert [item.attribute_name for item in bundle.schema_attributes] == ["Height"]


def test_source_ir_row_and_transposed_preparation():
    variety = _attribute("Variety", ("Domba", "Domba", "Gendot"), attribute_id="Sheet!COL:A")
    row_bundle = prepare_source_ir_runtime_source(
        _source_ir([variety, _attribute()]), anchor_detector=_anchor
    )
    assert row_bundle.backend == "source-ir"
    assert row_bundle.anchor_attribute_id == "Sheet!COL:A"
    assert row_bundle.position_to_variety == ["Domba", "Domba", "Gendot"]
    assert [item.attribute_name for item in row_bundle.schema_attributes] == ["Height"]

    transposed = prepare_source_ir_runtime_source(
        _source_ir([_attribute()], orientation="transposed", entities=["Domba", "Gendot", "Domba"])
    )
    assert transposed.position_to_variety == ["Domba", "Gendot", "Domba"]
    assert transposed.variety_names == ["Domba", "Gendot"]


def test_source_ir_anchor_name_ambiguity_fails_closed():
    first = _attribute("Variety", ("A", "B", "C"), attribute_id="Sheet!COL:A")
    second = _attribute("Variety", ("A", "B", "C"), attribute_id="Sheet!COL:B")
    with pytest.raises(RuntimeSourcePreparationError, match="AMBIGUOUS_ANCHOR_ATTRIBUTE"):
        prepare_source_ir_runtime_source(_source_ir([first, second]), anchor_detector=_anchor)


def test_coordinate_aware_grouping_preserves_blanks_and_all_source_evidence():
    attribute = runtime_attribute_from_source_ir(_attribute(values=("10", None, "12")))
    grouped = group_attribute_contributions_by_variety(
        attribute, ["Domba", "Gendot", "Domba"]
    )
    assert [item.position_index for item in grouped["Domba"]] == [0, 2]
    assert [item.raw_value for item in grouped["Domba"]] == ["10", "12"]
    assert physical_source_cells(grouped["Domba"]) == ["B2", "B4"]
    assert "Gendot" not in grouped


def test_physical_cell_dedup_keeps_distinct_observations_but_one_merged_anchor():
    attribute = RuntimeSourceAttribute(
        attribute_name="Height",
        structural_context=None,
        row_values=["10", "10"],
        source_attribute_id="Sheet!COL:B",
        logical_value_coordinates=["B2", "B3"],
        physical_value_coordinates=["B2", "B2"],
    )
    contributions = group_attribute_contributions_by_variety(
        attribute, ["Domba", "Domba"]
    )["Domba"]
    assert len(contributions) == 2
    assert physical_source_cells(contributions) == ["B2"]
