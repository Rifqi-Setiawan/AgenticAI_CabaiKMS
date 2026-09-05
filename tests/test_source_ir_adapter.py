from src.ingestion.source_ir_adapter import (
    source_ir_entity_names,
    source_ir_to_parsed_attributes,
)
from src.schema.source_ir import SourceIR


def _source_ir(orientation="row-oriented"):
    positions = (
        [{"position_index": 0, "row": 2}, {"position_index": 1, "row": 3}]
        if orientation == "row-oriented"
        else [
            {
                "position_index": 0,
                "column_letter": "B",
                "header_coordinate": "B1",
                "raw_entity_label": " Domba ",
            },
            {
                "position_index": 1,
                "column_letter": "C",
                "header_coordinate": "C1",
                "raw_entity_label": None,
            },
        ]
    )
    return SourceIR(
        source_file_name="fixture.xlsx",
        source_file_sha256="abc",
        sheet_name="Sheet",
        tables=[{
            "table_index": 0,
            "sheet_name": "Sheet",
            "table_range": "A1:C3",
            "orientation": orientation,
            "observation_positions": positions,
            "attributes": [{
                "source_attribute_id": "Sheet!COL:B",
                "axis": "column" if orientation == "row-oriented" else "row",
                "axis_coordinate": "B",
                "raw_label": " Length ",
                "header_path": ["Fruit", "Length"],
                "header_cells": ["B1"],
                "structural_context": "Fruit",
                "detected_value_type": "mixed",
                "values": [
                    {"position_index": 0, "coordinate": "B2", "raw_value": 80, "value_type": "integer"},
                    {"position_index": 1, "coordinate": "B3", "raw_value": None, "value_type": "empty"},
                ],
            }],
            "structure_confidence": 0.8,
        }],
    )


def test_source_ir_projects_to_legacy_string_values_without_dropping_blanks():
    parsed = source_ir_to_parsed_attributes(_source_ir())[0]
    assert parsed.attribute_name == "Length"
    assert parsed.structural_context == "Fruit"
    assert parsed.row_values == ["80", None]


def test_transposed_entity_adapter_preserves_order_and_none():
    assert source_ir_entity_names(_source_ir("transposed")) == ["Domba", None]
