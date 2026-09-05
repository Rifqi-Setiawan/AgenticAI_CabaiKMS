"""Backend-neutral runtime source attributes and deterministic preparation helpers."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from src.agents.schema_matching.anchor import AnchorCandidate, AnchorResult, detect_anchor
from src.agents.schema_matching.source_parsing import (
    ParsedAttribute,
    load_row_oriented_columns,
    load_transposed_rows,
)
from src.schema.shadow_parity import ShadowParityReport
from src.schema.source_ir import SourceAttributeIR, SourceIR

SourceFormat = Literal["row-oriented", "transposed"]
SourceBackend = Literal["legacy", "source-ir"]
AnchorDetector = Callable[..., AnchorResult]


class RuntimeSourcePreparationError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass
class RuntimeSourceAttribute:
    attribute_name: str
    structural_context: str | None
    row_values: list[str | None]
    source_attribute_id: str | None = None
    header_cells: list[str] = field(default_factory=list)
    logical_value_coordinates: list[str | None] = field(default_factory=list)
    physical_value_coordinates: list[str | None] = field(default_factory=list)
    detected_value_type: str | None = None

    def __post_init__(self) -> None:
        coordinate_backed = (
            self.source_attribute_id is not None
            or bool(self.logical_value_coordinates)
            or bool(self.physical_value_coordinates)
        )
        if coordinate_backed and (
            len(self.row_values) != len(self.logical_value_coordinates)
            or len(self.row_values) != len(self.physical_value_coordinates)
        ):
            raise ValueError(
                "Source IR runtime values and logical/physical coordinates must be positionally aligned"
            )

    @property
    def sample_values(self) -> list[str]:
        return [value for value in self.row_values if value is not None]

    @property
    def display_name(self) -> str:
        if self.structural_context:
            return f"{self.structural_context} / {self.attribute_name}"
        return self.attribute_name


@dataclass
class RuntimeSourceBundle:
    backend: SourceBackend
    source_format: SourceFormat
    all_attributes: list[RuntimeSourceAttribute]
    schema_attributes: list[RuntimeSourceAttribute]
    position_to_variety: list[str | None]
    variety_names: list[str]
    anchor_attribute_id: str | None = None
    anchor_attribute_name: str | None = None
    source_ir: SourceIR | None = None
    migration_report: ShadowParityReport | None = None


@dataclass(frozen=True)
class RuntimeValueContribution:
    position_index: int
    raw_value: str
    logical_coordinate: str | None
    physical_source_coordinate: str | None


def runtime_attribute_from_legacy(attribute: ParsedAttribute) -> RuntimeSourceAttribute:
    return RuntimeSourceAttribute(
        attribute_name=attribute.attribute_name,
        structural_context=attribute.structural_context,
        row_values=list(attribute.row_values),
    )


def runtime_attribute_from_source_ir(attribute: SourceAttributeIR) -> RuntimeSourceAttribute:
    return RuntimeSourceAttribute(
        attribute_name=str(attribute.raw_label).strip(),
        structural_context=attribute.structural_context,
        row_values=[
            None if value.raw_value is None else str(value.raw_value)
            for value in attribute.values
        ],
        source_attribute_id=attribute.source_attribute_id,
        header_cells=list(attribute.header_cells),
        logical_value_coordinates=[value.coordinate for value in attribute.values],
        physical_value_coordinates=[value.source_coordinate for value in attribute.values],
        detected_value_type=attribute.detected_value_type,
    )


def parsed_attribute_from_runtime(attribute: RuntimeSourceAttribute) -> ParsedAttribute:
    return ParsedAttribute(
        attribute_name=attribute.attribute_name,
        structural_context=attribute.structural_context,
        row_values=list(attribute.row_values),
    )


def _unique_varieties(position_to_variety: list[str | None]) -> list[str]:
    varieties: list[str] = []
    for value in position_to_variety:
        if value and value not in varieties:
            varieties.append(value)
    return varieties


def _validate_variety_positions(
    attributes: list[RuntimeSourceAttribute],
    position_to_variety: list[str | None],
) -> None:
    for index, variety in enumerate(position_to_variety):
        if not variety and any(
            index < len(attribute.row_values)
            and attribute.row_values[index] is not None
            and str(attribute.row_values[index]).strip()
            for attribute in attributes
        ):
            raise ValueError(
                f"Varietas kosong pada observasi ke-{index + 1}. "
                "Isi kolom varietas sebelum menjalankan pipeline."
            )


def _validate_attribute_position_lengths(
    attributes: list[RuntimeSourceAttribute],
    position_to_variety: list[str | None],
) -> None:
    mismatched = [
        attribute.display_name
        for attribute in attributes
        if len(attribute.row_values) != len(position_to_variety)
    ]
    if mismatched:
        raise RuntimeSourcePreparationError(
            "POSITION_ALIGNMENT_MISMATCH",
            "attributes do not align with the observation axis: " + ", ".join(mismatched),
        )


def prepare_legacy_runtime_source(
    file_path: Path,
    sheet_name: str,
    *,
    source_format: SourceFormat,
    header_rows: int | None = None,
    anchor_detector: AnchorDetector | None = None,
) -> RuntimeSourceBundle:
    detector = anchor_detector or detect_anchor
    if source_format == "row-oriented":
        parsed = load_row_oriented_columns(file_path, sheet_name, header_rows=header_rows)
        candidates = [AnchorCandidate(item.attribute_name, item.sample_values) for item in parsed]
        anchor = detector(candidates, source_format="row-oriented")
        anchor_attribute = next(
            (item for item in parsed if item.attribute_name == anchor.column_name), None
        )
        if anchor.status != "found" or anchor_attribute is None:
            raise ValueError(
                "Kolom varietas tidak ditemukan. Periksa jumlah baris header dan "
                "nama kolom identitas (misalnya Variety atau Jenis Cabai). "
                "Proses dihentikan agar tidak menghasilkan workbook kosong."
            )
        position_to_variety = [
            value.strip() if value is not None else None
            for value in anchor_attribute.row_values
        ]
        runtime = [runtime_attribute_from_legacy(item) for item in parsed]
        _validate_attribute_position_lengths(runtime, position_to_variety)
        _validate_variety_positions(runtime, position_to_variety)
        schema_attributes = [
            item for item in runtime if item.attribute_name != anchor.column_name
        ]
        return RuntimeSourceBundle(
            backend="legacy",
            source_format=source_format,
            all_attributes=runtime,
            schema_attributes=schema_attributes,
            position_to_variety=position_to_variety,
            variety_names=_unique_varieties(position_to_variety),
            anchor_attribute_name=anchor.column_name,
        )

    parsed, entity_names = load_transposed_rows(file_path, sheet_name)
    runtime = [runtime_attribute_from_legacy(item) for item in parsed]
    position_to_variety = list(entity_names)
    _validate_attribute_position_lengths(runtime, position_to_variety)
    return RuntimeSourceBundle(
        backend="legacy",
        source_format=source_format,
        all_attributes=runtime,
        schema_attributes=runtime,
        position_to_variety=position_to_variety,
        variety_names=_unique_varieties(position_to_variety),
    )


def prepare_source_ir_runtime_source(
    source_ir: SourceIR,
    *,
    anchor_detector: AnchorDetector | None = None,
    migration_report: ShadowParityReport | None = None,
) -> RuntimeSourceBundle:
    if len(source_ir.tables) != 1:
        raise RuntimeSourcePreparationError(
            "SOURCE_IR_TABLE_COUNT_UNSUPPORTED", "exactly one source table is required"
        )
    table = source_ir.tables[0]
    runtime = [runtime_attribute_from_source_ir(item) for item in table.attributes]
    if table.orientation == "row-oriented":
        detector = anchor_detector or detect_anchor
        anchor = detector(
            [AnchorCandidate(item.attribute_name, item.sample_values) for item in runtime],
            source_format="row-oriented",
        )
        if anchor.status != "found" or anchor.column_name is None:
            raise RuntimeSourcePreparationError(
                "ANCHOR_NOT_FOUND", "Source IR row-oriented anchor was not found"
            )
        matches = [item for item in runtime if item.attribute_name == anchor.column_name]
        if len(matches) != 1:
            raise RuntimeSourcePreparationError(
                "AMBIGUOUS_ANCHOR_ATTRIBUTE",
                f"anchor name {anchor.column_name!r} selects {len(matches)} attributes",
            )
        anchor_attribute = matches[0]
        position_to_variety = [
            value.strip() if value is not None else None
            for value in anchor_attribute.row_values
        ]
        _validate_attribute_position_lengths(runtime, position_to_variety)
        _validate_variety_positions(runtime, position_to_variety)
        schema_attributes = [item for item in runtime if item is not anchor_attribute]
        return RuntimeSourceBundle(
            backend="source-ir",
            source_format="row-oriented",
            all_attributes=runtime,
            schema_attributes=schema_attributes,
            position_to_variety=position_to_variety,
            variety_names=_unique_varieties(position_to_variety),
            anchor_attribute_id=anchor_attribute.source_attribute_id,
            anchor_attribute_name=anchor_attribute.attribute_name,
            source_ir=source_ir,
            migration_report=migration_report,
        )

    position_to_variety = [
        None if item.raw_entity_label is None else str(item.raw_entity_label).strip()
        for item in table.observation_positions
    ]
    _validate_attribute_position_lengths(runtime, position_to_variety)
    _validate_variety_positions(runtime, position_to_variety)
    return RuntimeSourceBundle(
        backend="source-ir",
        source_format="transposed",
        all_attributes=runtime,
        schema_attributes=runtime,
        position_to_variety=position_to_variety,
        variety_names=_unique_varieties(position_to_variety),
        source_ir=source_ir,
        migration_report=migration_report,
    )


def group_attribute_contributions_by_variety(
    attribute: RuntimeSourceAttribute,
    position_to_variety: list[str | None],
) -> dict[str, list[RuntimeValueContribution]]:
    if len(attribute.row_values) != len(position_to_variety):
        raise ValueError("attribute values and variety positions must have identical lengths")
    if attribute.source_attribute_id is not None and (
        len(attribute.row_values) != len(attribute.logical_value_coordinates)
        or len(attribute.row_values) != len(attribute.physical_value_coordinates)
    ):
        raise ValueError("Source IR contribution coordinates are not positionally aligned")
    grouped: dict[str, list[RuntimeValueContribution]] = {}
    for index, (raw_value, variety) in enumerate(
        zip(attribute.row_values, position_to_variety)
    ):
        if raw_value is None or variety is None:
            continue
        logical = (
            attribute.logical_value_coordinates[index]
            if attribute.logical_value_coordinates
            else None
        )
        physical = (
            attribute.physical_value_coordinates[index]
            if attribute.physical_value_coordinates
            else None
        )
        grouped.setdefault(variety, []).append(
            RuntimeValueContribution(
                position_index=index,
                raw_value=raw_value,
                logical_coordinate=logical,
                physical_source_coordinate=physical,
            )
        )
    return grouped


def physical_source_cells(
    contributions: list[RuntimeValueContribution],
) -> list[str]:
    cells: list[str] = []
    for item in contributions:
        coordinate = item.physical_source_coordinate
        if coordinate is not None and coordinate not in cells:
            cells.append(coordinate)
    return cells
