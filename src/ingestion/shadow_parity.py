"""Deterministic comparison of authoritative legacy parsing and shadow Source IR."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from src.agents.schema_matching.anchor import AnchorCandidate, AnchorResult, detect_anchor
from src.agents.schema_matching.source_parsing import ParsedAttribute
from src.ingestion.source_ir_adapter import (
    source_ir_entity_names,
    source_ir_to_parsed_attributes,
)
from src.schema.shadow_parity import (
    AttributeParity,
    PositionMismatch,
    ShadowParityReport,
    ShadowStatus,
)
from src.schema.source_ir import SourceIR

MAX_REPORTED_POSITION_MISMATCHES = 20
AnchorDetector = Callable[..., AnchorResult]


def _normalized(value: str | None) -> str:
    return (value or "").strip().casefold()


def _key(attribute: ParsedAttribute) -> tuple[str, str]:
    return _normalized(attribute.structural_context), _normalized(attribute.attribute_name)


def _display(attribute: ParsedAttribute) -> str:
    return attribute.display_name.strip()


def _value_comparison(
    legacy_values: list[str | None],
    source_values: list[str | None],
) -> tuple[int, int, list[PositionMismatch]]:
    matching = 0
    differing = 0
    details: list[PositionMismatch] = []
    for index in range(max(len(legacy_values), len(source_values))):
        legacy_present = index < len(legacy_values)
        source_present = index < len(source_values)
        legacy = legacy_values[index] if legacy_present else None
        source = source_values[index] if source_present else None
        if legacy_present and source_present and legacy == source:
            matching += 1
            continue
        differing += 1
        if len(details) < MAX_REPORTED_POSITION_MISMATCHES:
            details.append(
                PositionMismatch(
                    position_index=index,
                    legacy_value=legacy,
                    source_ir_value=source,
                )
            )
    return matching, differing, details


def _anchor_identity(
    result: AnchorResult,
    attributes: list[ParsedAttribute],
) -> tuple[str | None, ParsedAttribute | None]:
    if result.status != "found" or result.column_name is None:
        return None, None
    matches = [item for item in attributes if item.attribute_name == result.column_name]
    if len(matches) != 1:
        return None, None
    return _display(matches[0]), matches[0]


def compare_shadow_parity(
    legacy_attributes: list[ParsedAttribute],
    source_ir: SourceIR,
    *,
    source_format: str,
    legacy_entity_names: list[str] | None = None,
    anchor_detector: AnchorDetector | None = None,
) -> ShadowParityReport:
    """Compare exact legacy-compatible logical output; never invoke an LLM."""
    if source_format not in {"row-oriented", "transposed"}:
        raise ValueError(f"unsupported source format: {source_format!r}")
    table = source_ir.tables[0] if len(source_ir.tables) == 1 else None
    if table is None:
        return ShadowParityReport(
            status=ShadowStatus.NOT_COMPARABLE,
            source_format=source_format,
            issue_codes=["SOURCE_IR_TABLE_COUNT_UNSUPPORTED"],
            summary="NOT_COMPARABLE — Source IR must contain exactly one table",
        )

    adapted = source_ir_to_parsed_attributes(source_ir)
    legacy_keys = [_key(item) for item in legacy_attributes]
    source_keys = [_key(item) for item in adapted]
    legacy_counts = Counter(legacy_keys)
    source_counts = Counter(source_keys)
    duplicate_keys = {
        key for key, count in legacy_counts.items() if count > 1
    } | {key for key, count in source_counts.items() if count > 1}
    if duplicate_keys:
        return ShadowParityReport(
            status=ShadowStatus.NOT_COMPARABLE,
            source_format=source_format,
            new_orientation=table.orientation,
            orientation_match=source_format == table.orientation,
            issue_codes=["AMBIGUOUS_ATTRIBUTE_IDENTITY"],
            new_path_resolved=True,
            legacy_attribute_count=len(legacy_attributes),
            source_ir_attribute_count=len(adapted),
            summary="NOT_COMPARABLE — duplicate full logical attribute identity",
        )

    legacy_by_key = {key: (index, item) for index, (key, item) in enumerate(zip(legacy_keys, legacy_attributes))}
    source_by_key = {key: (index, item) for index, (key, item) in enumerate(zip(source_keys, adapted))}
    shared = set(legacy_by_key) & set(source_by_key)
    legacy_only = [
        _display(item) for key, item in zip(legacy_keys, legacy_attributes) if key not in shared
    ]
    source_only = [
        _display(item) for key, item in zip(source_keys, adapted) if key not in shared
    ]
    order_match = legacy_keys == source_keys
    details: list[AttributeParity] = []
    total_positions = matching_positions = differing_positions = 0
    full_value_matches = 0
    for key in legacy_keys:
        if key not in shared:
            continue
        legacy_index, legacy = legacy_by_key[key]
        source_index, source = source_by_key[key]
        matching, differing, mismatches = _value_comparison(
            legacy.row_values, source.row_values
        )
        total_positions += max(len(legacy.row_values), len(source.row_values))
        matching_positions += matching
        differing_positions += differing
        if differing == 0:
            full_value_matches += 1
        details.append(
            AttributeParity(
                legacy_identity=_display(legacy),
                source_ir_identity=_display(source),
                legacy_index=legacy_index,
                source_ir_index=source_index,
                identity_match=True,
                context_match=_normalized(legacy.structural_context)
                == _normalized(source.structural_context),
                order_match=legacy_index == source_index,
                legacy_value_count=len(legacy.row_values),
                source_ir_value_count=len(source.row_values),
                matching_positions=matching,
                differing_positions=differing,
                values_match=differing == 0,
                position_mismatches=mismatches,
            )
        )

    issues: list[str] = []
    orientation_match = source_format == table.orientation
    if not orientation_match:
        issues.append("ORIENTATION_MISMATCH")
    if len(legacy_attributes) != len(adapted):
        issues.append("ATTRIBUTE_COUNT_MISMATCH")
    if legacy_only or source_only:
        issues.append("ATTRIBUTE_IDENTITY_MISMATCH")
    if not order_match:
        issues.append("ATTRIBUTE_ORDER_MISMATCH")
    if differing_positions:
        issues.append("VALUE_POSITION_MISMATCH")

    legacy_anchor_status = source_anchor_status = None
    legacy_anchor_identity = source_anchor_identity = None
    anchor_match = anchor_values_match = None
    entity_names_match = None
    entity_mismatches: list[PositionMismatch] = []
    if source_format == "row-oriented":
        if table.orientation == "row-oriented":
            detector = anchor_detector or detect_anchor
            legacy_anchor = detector(
                [AnchorCandidate(item.attribute_name, item.sample_values) for item in legacy_attributes],
                source_format="row-oriented",
            )
            source_anchor = detector(
                [AnchorCandidate(item.attribute_name, item.sample_values) for item in adapted],
                source_format="row-oriented",
            )
            legacy_anchor_status = legacy_anchor.status
            source_anchor_status = source_anchor.status
            legacy_anchor_identity, legacy_anchor_attribute = _anchor_identity(
                legacy_anchor, legacy_attributes
            )
            source_anchor_identity, source_anchor_attribute = _anchor_identity(source_anchor, adapted)
            anchor_match = (
                legacy_anchor.status == source_anchor.status
                and legacy_anchor_identity == source_anchor_identity
            )
            if legacy_anchor.status == source_anchor.status == "found":
                anchor_values_match = False
                if legacy_anchor_attribute is not None and source_anchor_attribute is not None:
                    _, anchor_differences, _ = _value_comparison(
                        legacy_anchor_attribute.row_values,
                        source_anchor_attribute.row_values,
                    )
                    anchor_values_match = anchor_differences == 0
                if legacy_anchor_identity is None or source_anchor_identity is None:
                    issues.append("ANCHOR_IDENTITY_AMBIGUOUS")
            else:
                anchor_match = False
                issues.append("ANCHOR_NOT_FOUND")
            if not anchor_match:
                issues.append("ANCHOR_IDENTITY_MISMATCH")
            if anchor_values_match is False:
                issues.append("ANCHOR_VALUE_MISMATCH")
        else:
            anchor_match = False
    else:
        if table.orientation == "transposed":
            legacy_entities = list(legacy_entity_names or [])
            source_entities = source_ir_entity_names(source_ir)
            _, entity_differences, entity_mismatches = _value_comparison(
                legacy_entities, source_entities
            )
            entity_names_match = entity_differences == 0
            if not entity_names_match:
                issues.append("ENTITY_POSITION_MISMATCH")
        else:
            entity_names_match = False

    matched = len(shared)
    identity_rate = matched / max(len(legacy_attributes), len(adapted)) if max(len(legacy_attributes), len(adapted)) else None
    value_rate = matching_positions / total_positions if total_positions else None
    status = ShadowStatus.MATCH if not issues else ShadowStatus.DIFFERENT
    summary = (
        f"{status.value} — {matched} matched attributes, "
        f"{total_positions} value positions checked, {differing_positions} differing"
    )
    return ShadowParityReport(
        status=status,
        source_format=source_format,
        new_orientation=table.orientation,
        orientation_match=orientation_match,
        issue_codes=issues,
        new_path_resolved=True,
        legacy_attribute_count=len(legacy_attributes),
        source_ir_attribute_count=len(adapted),
        matched_attribute_count=matched,
        attribute_identity_matches=matched,
        attribute_context_matches=sum(item.context_match for item in details),
        attributes_with_full_value_match=full_value_matches,
        total_value_positions_compared=total_positions,
        matching_value_positions=matching_positions,
        differing_value_positions=differing_positions,
        legacy_only_count=len(legacy_only),
        source_ir_only_count=len(source_only),
        attribute_identity_parity=identity_rate,
        value_position_parity=value_rate,
        order_match=order_match,
        attributes=details,
        legacy_only_attributes=legacy_only,
        source_ir_only_attributes=source_only,
        legacy_anchor_status=legacy_anchor_status,
        source_ir_anchor_status=source_anchor_status,
        legacy_anchor_identity=legacy_anchor_identity,
        source_ir_anchor_identity=source_anchor_identity,
        anchor_match=anchor_match,
        anchor_values_match=anchor_values_match,
        entity_names_match=entity_names_match,
        entity_position_mismatches=entity_mismatches,
        summary=summary,
    )
