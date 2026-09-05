"""Deterministically build coordinate-preserving Source IR from verified structure."""

from __future__ import annotations

from typing import Any

from src.ingestion.structure_geometry import cell_lookup, resolve_profile_cell
from src.ingestion.structure_verifier import verify_structure
from src.ingestion.workbook_profiler import CellProfile, SheetProfile, WorkbookProfile
from src.schema.source_ir import (
    DetectedValueType,
    SourceAttributeIR,
    SourceIR,
    SourceObservationPosition,
    SourceTableIR,
    SourceValueIR,
)
from src.schema.structure import VerifiedStructure


def _sheet(profile: WorkbookProfile, name: str) -> SheetProfile:
    try:
        return next(sheet for sheet in profile.sheets if sheet.sheet_name == name)
    except StopIteration as exc:
        raise ValueError(f"sheet {name!r} is not present in WorkbookProfile") from exc


def _source_value(
    sheet: SheetProfile,
    lookup: dict[str, CellProfile],
    coordinate: str,
    position_index: int,
) -> SourceValueIR:
    resolved = resolve_profile_cell(sheet, coordinate, cells_by_coordinate=lookup)
    cell = resolved[1] if resolved is not None else None
    return SourceValueIR(
        position_index=position_index,
        coordinate=coordinate,
        raw_value=cell.value if cell is not None else None,
        value_type=cell.value_type if cell is not None else "empty",
    )


def _detected(values: list[SourceValueIR]) -> DetectedValueType:
    groups = []
    for value in values:
        if value.value_type == "empty":
            continue
        if value.value_type in {"integer", "float"}:
            groups.append("numeric")
        elif value.value_type == "string":
            groups.append("text")
        elif value.value_type == "boolean":
            groups.append("boolean")
        elif value.value_type in {"date", "datetime", "time"}:
            groups.append("temporal")
        elif value.value_type == "formula":
            groups.append("formula")
        else:
            groups.append("mixed")
    kinds = set(groups)
    if not kinds:
        return "empty"
    if len(kinds) == 1 and "mixed" not in kinds:
        return next(iter(kinds))  # type: ignore[return-value]
    return "mixed"


def _resolved_header(
    sheet: SheetProfile,
    lookup: dict[str, CellProfile],
    coordinates: list[str],
) -> tuple[list[Any], list[str]]:
    path: list[Any] = []
    source_coordinates: list[str] = []
    for coordinate in coordinates:
        resolved = resolve_profile_cell(sheet, coordinate, cells_by_coordinate=lookup)
        if resolved is None:
            raise ValueError(f"verified header coordinate {coordinate!r} cannot be resolved")
        source_coordinate, cell = resolved
        path.append(cell.value)
        source_coordinates.append(source_coordinate)
    return path, source_coordinates


def _row_table(sheet: SheetProfile, verified: VerifiedStructure) -> SourceTableIR:
    proposal = verified.proposal
    structure = proposal.row_oriented
    assert structure is not None
    lookup = cell_lookup(sheet)
    bindings = {
        binding.column_letter.replace("$", "").upper(): binding
        for binding in structure.header_bindings
    }
    positions = [
        SourceObservationPosition(position_index=index, row=row)
        for index, row in enumerate(range(structure.data_start_row, structure.data_end_row + 1))
    ]
    attributes: list[SourceAttributeIR] = []
    for raw_column in structure.attribute_columns:
        column = raw_column.replace("$", "").upper()
        binding = bindings[column]
        path, header_cells = _resolved_header(sheet, lookup, binding.header_cells)
        values = [
            _source_value(sheet, lookup, f"{column}{position.row}", position.position_index)
            for position in positions
            if position.row is not None
        ]
        attributes.append(
            SourceAttributeIR(
                source_attribute_id=f"{sheet.sheet_name}!COL:{column}",
                axis="column",
                axis_coordinate=column,
                raw_label=path[-1],
                header_path=path,
                header_cells=header_cells,
                structural_context=" / ".join(str(item) for item in path[:-1]) or None,
                detected_value_type=_detected(values),
                values=values,
            )
        )
    return SourceTableIR(
        table_index=0,
        sheet_name=sheet.sheet_name,
        table_range=structure.table_range,
        orientation="row-oriented",
        observation_positions=positions,
        attributes=attributes,
        structure_confidence=proposal.confidence,
        structure_reason_codes=proposal.reason_codes,
    )


def _transposed_table(sheet: SheetProfile, verified: VerifiedStructure) -> SourceTableIR:
    proposal = verified.proposal
    structure = proposal.transposed
    assert structure is not None
    lookup = cell_lookup(sheet)
    columns = [column.replace("$", "").upper() for column in structure.data_columns]
    positions: list[SourceObservationPosition] = []
    for index, column in enumerate(columns):
        coordinate = f"{column}{structure.header_row}"
        resolved = resolve_profile_cell(sheet, coordinate, cells_by_coordinate=lookup)
        if resolved is None:
            raise ValueError(f"verified entity header {coordinate!r} cannot be resolved")
        positions.append(
            SourceObservationPosition(
                position_index=index,
                column_letter=column,
                header_coordinate=resolved[0],
                raw_entity_label=resolved[1].value,
            )
        )
    label_column = structure.label_column.replace("$", "").upper()
    attributes: list[SourceAttributeIR] = []
    for row in range(structure.attribute_start_row, structure.attribute_end_row + 1):
        label_coordinate = f"{label_column}{row}"
        resolved_label = resolve_profile_cell(sheet, label_coordinate, cells_by_coordinate=lookup)
        if resolved_label is None:
            continue
        values = [
            _source_value(sheet, lookup, f"{column}{row}", index)
            for index, column in enumerate(columns)
        ]
        attributes.append(
            SourceAttributeIR(
                source_attribute_id=f"{sheet.sheet_name}!ROW:{row}",
                axis="row",
                axis_coordinate=str(row),
                raw_label=resolved_label[1].value,
                header_path=[resolved_label[1].value],
                header_cells=[resolved_label[0]],
                structural_context=None,
                detected_value_type=_detected(values),
                values=values,
            )
        )
    return SourceTableIR(
        table_index=0,
        sheet_name=sheet.sheet_name,
        table_range=structure.table_range,
        orientation="transposed",
        observation_positions=positions,
        attributes=attributes,
        structure_confidence=proposal.confidence,
        structure_reason_codes=proposal.reason_codes,
    )


def build_source_ir(
    workbook_profile: WorkbookProfile,
    sheet_name: str,
    verified_structure: VerifiedStructure,
) -> SourceIR:
    """Build Source IR without reopening Excel or invoking probabilistic services."""
    sheet = _sheet(workbook_profile, sheet_name)
    proposal = verified_structure.proposal
    current_verification = verify_structure(sheet, proposal)
    if not current_verification.valid:
        raise ValueError(
            "verified structure is not valid for the selected WorkbookProfile sheet: "
            + ", ".join(current_verification.issue_codes)
        )
    table = (
        _row_table(sheet, verified_structure)
        if proposal.orientation == "row-oriented"
        else _transposed_table(sheet, verified_structure)
    )
    return SourceIR(
        source_file_name=workbook_profile.source_file_name,
        source_file_sha256=workbook_profile.source_file_sha256,
        sheet_name=sheet_name,
        tables=[table],
    )
