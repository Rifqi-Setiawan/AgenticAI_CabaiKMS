"""Versioned, deterministic intermediate representation of verified source data."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.schema.structure import STRUCTURE_CONTRACT_VERSION, Orientation

SOURCE_IR_VERSION = "source-ir-v1"
PROFILE_VERSION = "workbook-structure-v1"
SourceValueType = Literal[
    "empty", "string", "integer", "float", "boolean", "date", "datetime", "time", "formula", "other"
]
DetectedValueType = Literal["numeric", "text", "boolean", "temporal", "formula", "mixed", "empty"]


class SourceValueIR(BaseModel):
    position_index: int
    coordinate: str
    source_coordinate: str | None = None
    raw_value: Any = None
    value_type: SourceValueType


class SourceObservationPosition(BaseModel):
    position_index: int
    row: int | None = None
    column_letter: str | None = None
    header_coordinate: str | None = None
    raw_entity_label: Any = None


class SourceAttributeIR(BaseModel):
    source_attribute_id: str
    axis: Literal["column", "row"]
    axis_coordinate: str
    raw_label: Any
    header_path: list[Any]
    header_cells: list[str]
    structural_context: str | None = None
    detected_value_type: DetectedValueType
    values: list[SourceValueIR]


class SourceTableIR(BaseModel):
    table_index: int
    sheet_name: str
    table_range: str
    orientation: Orientation
    observation_positions: list[SourceObservationPosition]
    attributes: list[SourceAttributeIR]
    structure_confidence: float
    structure_reason_codes: list[str] = Field(default_factory=list)


class SourceIR(BaseModel):
    ir_version: Literal["source-ir-v1"] = SOURCE_IR_VERSION
    source_file_name: str
    source_file_sha256: str
    workbook_profile_version: Literal["workbook-structure-v1"] = PROFILE_VERSION
    structure_contract_version: Literal["structure-understanding-v1"] = STRUCTURE_CONTRACT_VERSION
    sheet_name: str
    tables: list[SourceTableIR]
