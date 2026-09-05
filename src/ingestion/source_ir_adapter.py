"""Lossy compatibility projection from coordinate-rich Source IR to legacy shapes."""

from __future__ import annotations

from src.agents.schema_matching.source_parsing import ParsedAttribute
from src.schema.source_ir import SourceIR, SourceTableIR


def _one_table(source_ir: SourceIR) -> SourceTableIR:
    if len(source_ir.tables) != 1:
        raise ValueError("legacy compatibility requires exactly one SourceTableIR")
    return source_ir.tables[0]


def source_ir_to_parsed_attributes(source_ir: SourceIR) -> list[ParsedAttribute]:
    """Project Source IR values to the string-or-None legacy parser surface."""
    table = _one_table(source_ir)
    return [
        ParsedAttribute(
            attribute_name=str(attribute.raw_label).strip(),
            structural_context=attribute.structural_context,
            row_values=[
                None if value.raw_value is None else str(value.raw_value)
                for value in attribute.values
            ],
        )
        for attribute in table.attributes
    ]


def source_ir_entity_names(source_ir: SourceIR) -> list[str | None]:
    """Project transposed observation labels without normalization or deduplication."""
    table = _one_table(source_ir)
    if table.orientation != "transposed":
        raise ValueError("entity-name compatibility is only defined for transposed Source IR")
    return [
        None if position.raw_entity_label is None else str(position.raw_entity_label).strip()
        for position in table.observation_positions
    ]
